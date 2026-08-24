import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "AI Data Analyst Agent",
  description: "Upload a CSV or connect a database, ask questions in plain English.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
