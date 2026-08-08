app.tsx
'use client';

import { useMemo } from 'react';
import { TokenSource } from 'livekit-client';
import { useSession } from '@livekit/components-react';
import { WarningIcon } from '@phosphor-icons/react/dist/ssr';

import type { AppConfig } from '@/app-config';
import { AgentSessionProvider } from '@/components/agents-ui/agent-session-provider';
import { StartAudioButton } from '@/components/agents-ui/start-audio-button';
import { ViewController } from '@/components/app/view-controller';
import { Toaster } from '@/components/ui/sonner';
import { useAgentErrors } from '@/hooks/useAgentErrors';
import { useDebugMode } from '@/hooks/useDebug';
import { getSandboxTokenSource } from '@/lib/utils';

const IN_DEVELOPMENT = process.env.NODE_ENV !== 'production';

function AppSetup() {
  useDebugMode({ enabled: IN_DEVELOPMENT });
  useAgentErrors();

  return null;
}

interface AppProps {
  appConfig: AppConfig;
}

export function App({ appConfig }: AppProps) {
  const tokenSource = useMemo(() => {
    return typeof process.env.NEXT_PUBLIC_CONN_DETAILS_ENDPOINT === 'string'
      ? getSandboxTokenSource(appConfig)
      : TokenSource.endpoint('/api/token');
  }, [appConfig]);

  const session = useSession(
    tokenSource,
    appConfig.agentName ? { agentName: appConfig.agentName } : undefined
  );

  return (
    <AgentSessionProvider session={session}>
      <AppSetup />

      <main
        className="
          relative grid min-h-svh grid-cols-1 place-content-center
          overflow-hidden px-3 py-4 sm:px-6
          bg-gradient-to-br
          from-orange-100
          via-rose-50
          to-purple-100
          dark:from-orange-950
          dark:via-rose-950
          dark:to-purple-950
        "
      >
        {/* Top-left sunset glow */}
        <div
          className="
            pointer-events-none absolute
            -left-32 -top-32
            size-96 rounded-full
            bg-orange-300/40
            blur-3xl
            dark:bg-orange-500/15
          "
        />

        {/* Bottom-right purple glow */}
        <div
          className="
            pointer-events-none absolute
            -bottom-32 -right-32
            size-96 rounded-full
            bg-purple-300/40
            blur-3xl
            dark:bg-purple-500/15
          "
        />

        {/* Soft pink center glow */}
        <div
          className="
            pointer-events-none absolute
            left-1/2 top-1/2
            size-[500px]
            -translate-x-1/2
            -translate-y-1/2
            rounded-full
            bg-rose-200/20
            blur-3xl
            dark:bg-rose-500/5
          "
        />

        {/* Subtle light overlay */}
        <div
          className="
            pointer-events-none absolute inset-0
            bg-[radial-gradient(
              circle_at_center,
              rgba(255,255,255,0.35),
              transparent_55%
            )]
            dark:bg-[radial-gradient(
              circle_at_center,
              rgba(255,255,255,0.04),
              transparent_55%
            )]
          "
        />

        {/* Main application */}
        <div className="relative z-10">
          <ViewController appConfig={appConfig} />
        </div>
      </main>

      <StartAudioButton label="Start Audio" />

      <Toaster
        icons={{
          warning: <WarningIcon weight="bold" />,
        }}
        position="top-center"
        className="toaster group"
        style={
          {
            '--normal-bg': 'var(--popover)',
            '--normal-text': 'var(--popover-foreground)',
            '--normal-border': 'var(--border)',
          } as React.CSSProperties
        }
      />
    </AgentSessionProvider>
  );
}
