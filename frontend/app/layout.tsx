import type { Metadata } from "next";
import localFont from "next/font/local";
import "./globals.css";
import Footer from "@/components/Footer";

const pressStart = localFont({
  src: "../src/fonts/PressStart2P-Regular.ttf",
  variable: "--font-press-start",
  display: "swap",
});

const vt323 = localFont({
  src: "../src/fonts/VT323-Regular.ttf",
  variable: "--font-vt323",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Pixel Pebble",
  description: "Turn any photo into an 8-bit Pebble Time 2 watchface",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className={`${pressStart.variable} ${vt323.variable}`}>
        <main>{children}</main>
        <Footer />
      </body>
    </html>
  );
}
