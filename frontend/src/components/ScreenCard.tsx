import styles from "./pixel-ui.module.css";

export default function ScreenCard({
  stepLabel,
  title,
  tagline,
  children,
}: {
  stepLabel: string;
  title: string;
  tagline?: string;
  children: React.ReactNode;
}) {
  return (
    <div className={styles.screen}>
      <div className={`${styles.stepLabel} pixel-font`}>{stepLabel}</div>
      <h1 className={`${styles.logo} pixel-font`}>{title}</h1>
      {tagline && <div className={styles.tagline}>{tagline}</div>}
      {children}
    </div>
  );
}
