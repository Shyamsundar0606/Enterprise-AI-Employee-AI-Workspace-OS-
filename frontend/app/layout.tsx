import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = { title: "Enterprise AI Employee", description: "AI Workspace OS" };

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}
