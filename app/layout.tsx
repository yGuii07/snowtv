import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "SnowTV — Vídeos longos em cortes verticais",
  description:
    "Transforme vídeos longos em cortes verticais com seleção automática, legendas e rastreamento de rosto.",
  icons: {
    icon: "/favicon.svg",
    shortcut: "/favicon.svg",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="pt-BR">
      <body>{children}</body>
    </html>
  );
}
