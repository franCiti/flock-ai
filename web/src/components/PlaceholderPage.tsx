import styles from './PlaceholderPage.module.css';

/** A screen that is not built yet. */
export function PlaceholderPage({ title }: { title: string }) {
  return (
    <section className={styles.panel} aria-labelledby="page-title">
      <h1 id="page-title">{title}</h1>
      <p>Esta pantalla todavía no está disponible.</p>
    </section>
  );
}
