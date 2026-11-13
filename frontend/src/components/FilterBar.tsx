import { Search } from 'lucide-react';
import type { ReactNode } from 'react';
import styles from './FilterBar.module.css';

export function FilterBar({ children }: { children: ReactNode }) {
  return <div className={styles.bar}>{children}</div>;
}

export function SearchInput({
  value,
  onChange,
  placeholder = 'Search…',
}: {
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
}) {
  return (
    <div className={styles.search}>
      <Search size={15} className={styles.searchIcon} />
      <input
        className={styles.searchInput}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        type="search"
      />
    </div>
  );
}

export function FilterSelect({
  value,
  onChange,
  options,
  placeholder,
}: {
  value: string;
  onChange: (v: string) => void;
  options: { value: string; label: string }[];
  placeholder: string;
}) {
  return (
    <select className={styles.select} value={value} onChange={(e) => onChange(e.target.value)}>
      <option value="">{placeholder}</option>
      {options.map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  );
}
