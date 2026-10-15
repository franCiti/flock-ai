import { act, render, screen } from '@testing-library/react';
import { Countdown } from './Countdown.tsx';

describe('Countdown', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(0);
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('shows the time left and counts down to zero', () => {
    render(<Countdown deadline={65_000} />);
    expect(screen.getByRole('timer')).toHaveTextContent('1:05');

    act(() => {
      vi.advanceTimersByTime(2_000);
    });
    expect(screen.getByRole('timer')).toHaveTextContent('1:03');

    act(() => {
      vi.advanceTimersByTime(120_000);
    });
    expect(screen.getByRole('timer')).toHaveTextContent('0:00');
  });
});
