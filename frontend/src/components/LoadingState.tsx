"use client";

import { useEffect, useState } from "react";
import styles from "./pixel-ui.module.css";

export default function LoadingState({
  messages,
  spriteColor = "yellow",
}: {
  messages: string[];
  spriteColor?: "yellow" | "cyan";
}) {
  const [index, setIndex] = useState(0);

  useEffect(() => {
    const id = setInterval(() => {
      setIndex((i) => (i + 1) % messages.length);
    }, 2200);
    return () => clearInterval(id);
  }, [messages.length]);

  return (
    <div className={styles.loadingWrap}>
      <div className={`${styles.spriteBounce} ${spriteColor === "cyan" ? styles.cyan : ""}`} />
      <div className={styles.loadingBar}>
        <div className={styles.loadingBarFill} />
      </div>
      <div className={styles.loadingStatus}>{messages[index]}</div>
    </div>
  );
}
