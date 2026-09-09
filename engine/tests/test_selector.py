import unittest
from types import SimpleNamespace

from snow_engine.selector import HighlightSelector, build_candidates, fallback_title, semantic_similarity


def transcript_words(total=180):
    words = []
    vocabulary = ["Você", "precisa", "entender", "por", "que", "este", "erro", "muda", "tudo", "agora."]
    for index in range(total):
        start = index * 0.42
        words.append(SimpleNamespace(start=start, end=start + 0.34, word=vocabulary[index % len(vocabulary)]))
    return words


class SelectorTests(unittest.TestCase):
    def test_builds_candidates_inside_requested_duration(self):
        candidates = build_candidates(transcript_words(), "short")
        self.assertGreater(len(candidates), 1)
        self.assertTrue(all(12 <= candidate.end - candidate.start <= 34 for candidate in candidates))

    def test_local_selection_works_without_api(self):
        settings = SimpleNamespace(llm_provider="heuristic", llm_model="")
        selected = HighlightSelector(settings).select(transcript_words(), "auto", 3, "pt", "podcast")
        self.assertGreaterEqual(len(selected), 1)
        self.assertLessEqual(len(selected), 3)
        self.assertTrue(all(item.selection_method.startswith("heuristic-v4") for item in selected))
        self.assertTrue(all(0 <= item.score <= 100 for item in selected))
        self.assertTrue(all("hook" in item.score_breakdown for item in selected))
        self.assertTrue(all("boundary" in item.score_breakdown for item in selected))
        self.assertTrue(all(item.reason.endswith(".") for item in selected))

    def test_semantic_similarity_detects_near_duplicates(self):
        self.assertGreaterEqual(semantic_similarity("o maior erro muda seu resultado", "esse erro muda o resultado"), 0.5)
        self.assertLess(semantic_similarity("academia melhora disciplina", "receita de bolo com chocolate"), 0.2)

    def test_fallback_title_is_compact_and_not_transcript_dump(self):
        title = fallback_title("Você precisa entender por que esse erro destrói completamente o resultado no final.")
        self.assertLessEqual(len(title), 48)
        self.assertIn("por que", title.casefold())

    def test_fallback_title_does_not_use_generic_incidental_keyword(self):
        title = fallback_title("Eu gosto de assistir vídeos e entender como as pessoas contam histórias.")
        self.assertNotEqual(title, "Como isso muda tudo")
        self.assertTrue(title.startswith("Eu gosto de assistir"))

    def test_fallback_title_avoids_repeating_an_existing_title(self):
        text = "Aprender a gravar mudou minha rotina. Começar a treinar também melhorou minha confiança."
        first = fallback_title(text)
        second = fallback_title(text, [first])
        self.assertNotEqual(first.casefold(), second.casefold())

    def test_pause_contributes_to_natural_boundaries(self):
        words = []
        for index, word in enumerate("Este método explica uma ideia completa com clareza e resultado".split()):
            words.append(SimpleNamespace(start=index * .35, end=index * .35 + .24, word=word))
        offset = words[-1].end + 1.1
        for index, word in enumerate("Agora começa outro assunto diferente e independente para publicar.".split()):
            words.append(SimpleNamespace(start=offset + index * .35, end=offset + index * .35 + .24, word=word))
        candidates = build_candidates(words, "auto", "educational")
        self.assertTrue(candidates)
        self.assertTrue(all(item.start >= 0 and item.end > item.start for item in candidates))


if __name__ == "__main__":
    unittest.main()
