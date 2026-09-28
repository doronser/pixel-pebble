import styles from "./pixel-ui.module.css";

type Variant = "primary" | "secondary" | "ghost";

export default function PixelButton({
  variant = "primary",
  children,
  onClick,
  disabled,
  type = "button",
}: {
  variant?: Variant;
  children: React.ReactNode;
  onClick?: () => void;
  disabled?: boolean;
  type?: "button" | "submit";
}) {
  const variantClass =
    variant === "primary" ? styles.primary : variant === "secondary" ? styles.secondary : styles.ghost;
  return (
    <button
      type={type}
      className={`${styles.btn} ${variantClass} ${variant !== "ghost" ? "pixel-font" : ""}`}
      onClick={onClick}
      disabled={disabled}
    >
      {children}
    </button>
  );
}
