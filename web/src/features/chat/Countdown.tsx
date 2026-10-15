import { useEffect, useState } from 'react';
import { formatSeconds, secondsLeft } from './conversation.ts';
import styles from './ChatPage.module.css';

const TICK_MS = 250;

/** Time left until the agent stops trying (spec HU10.4). */
export function Countdown({ deadline }: { deadline: number }) {
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    const timer = setInterval(() => {
      setNow(Date.now());
    }, TICK_MS);
    return () => {
      clearInterval(timer);
    };
  }, []);

  return (
    <span className={styles.countdown} role="timer" aria-label="Tiempo restante">
      {formatSeconds(secondsLeft(deadline, now))}
    </span>
  );
}
