import type { ButtonHTMLAttributes } from 'react';
import { Loader2 } from 'lucide-react';
import styles from './Button.module.css';

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger';
type Size = 'sm' | 'md';

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
}

export function Button({ variant = 'secondary', size = 'md', loading, className, children, disabled, ...rest }: ButtonProps) {
  return (
    <button
      className={[styles.btn, styles[variant], styles[size], className].filter(Boolean).join(' ')}
      disabled={disabled || loading}
      {...rest}
    >
      {loading && <Loader2 size={14} className={styles.spinner} />}
      {children}
    </button>
  );
}
