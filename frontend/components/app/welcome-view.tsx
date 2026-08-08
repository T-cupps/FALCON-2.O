wlcome....
import { Compass, MapPin, Mic, Sparkles } from 'lucide-react';
import { Button } from '@/components/ui/button';

function WelcomeImage() {
  return (
    <div className="mb-6 flex size-24 items-center justify-center rounded-full bg-primary/10">
      <Compass className="size-12 text-primary" />
    </div>
  );
}

interface WelcomeViewProps {
  startButtonText: string;
  onStartCall: () => void;
  companyName?: string;
  mode?: 'ready' | 'connecting' | 'ended';
  isBusy?: boolean;
  errorMessage?: string | null;
}

const suggestions = [
  'Plan a trip',
  'Find places to visit',
  'Get travel tips',
  'Explore new destinations',
];

export const WelcomeView = ({
  startButtonText,
  onStartCall,
  companyName = 'Travel Companion',
  mode = 'ready',
  isBusy = false,
  errorMessage,
  ref,
}: React.ComponentProps<'div'> & WelcomeViewProps) => {
  const isConnecting = mode === 'connecting';
  const isEnded = mode === 'ended';

  const title = isConnecting
    ? 'Connecting to your travel companion...'
    : isEnded
      ? 'Travel session ended'
      : 'Your AI Travel Companion';

  const subtitle = isConnecting
    ? 'Please wait while we prepare your travel assistant.'
    : isEnded
      ? 'Your conversation has ended. Start again whenever you are ready.'
      : 'Plan your next adventure, one conversation at a time.';

  const body = isConnecting
    ? 'We are getting your voice travel companion ready for you.'
    : isEnded
      ? 'Your travel session has ended. Start again to continue exploring.'
      : 'Ask about destinations, plan your itinerary, discover places to visit, or get helpful travel tips with your AI travel companion.';

  return (
    <div className="flex min-h-screen items-center justify-center px-6 py-12">
      <section
        ref={ref}
        className="flex w-full max-w-3xl flex-col items-center text-center"
      >
        <WelcomeImage />

        <p className="mb-2 text-sm font-medium uppercase tracking-[0.25em] text-primary">
          {companyName}
        </p>

        <h1 className="text-3xl font-semibold tracking-tight text-foreground sm:text-4xl">
          {title}
        </h1>

        <p className="mt-3 max-w-2xl text-base leading-7 text-muted-foreground sm:text-lg">
          {subtitle}
        </p>

        <p className="mt-3 max-w-2xl text-sm leading-7 text-muted-foreground sm:text-base">
          {body}
        </p>

        {!isConnecting && !isEnded ? (
          <div className="mt-6 flex flex-wrap items-center justify-center gap-2">
            {suggestions.map((suggestion) => (
              <span
                key={suggestion}
                className="rounded-full border border-primary/15 bg-primary/5 px-3 py-1.5 text-sm text-foreground/80"
              >
                {suggestion}
              </span>
            ))}
          </div>
        ) : null}

        {errorMessage ? (
          <div className="mt-6 w-full max-w-xl rounded-2xl border border-amber-300/70 bg-amber-50 px-4 py-3 text-sm text-amber-800 dark:border-amber-500/40 dark:bg-amber-950/30 dark:text-amber-200">
            <p className="font-semibold">Microphone access is blocked.</p>
            <p className="mt-1">
              Please allow microphone access in your browser settings and try
              again.
            </p>
          </div>
        ) : null}

        <Button
          size="lg"
          onClick={onStartCall}
          disabled={isBusy}
          className="mt-8 min-w-[220px] rounded-full px-6 py-6 text-sm font-semibold tracking-[0.2em] uppercase"
          aria-label={isEnded ? 'Start again' : 'Start travel assistant'}
        >
          {isBusy
            ? 'Connecting...'
            : isEnded
              ? 'Start Again'
              : startButtonText}
        </Button>

        <div className="mt-8 flex flex-wrap items-center justify-center gap-4 text-sm text-muted-foreground">
          <span className="inline-flex items-center gap-2">
            <MapPin className="size-4 text-primary" />
            Discover destinations
          </span>

          <span className="inline-flex items-center gap-2">
            <Sparkles className="size-4 text-primary" />
            Plan your adventure
          </span>

          <span className="inline-flex items-center gap-2">
            <Mic className="size-4 text-primary" />
            Talk naturally
          </span>
        </div>
      </section>
    </div>
  );
};
