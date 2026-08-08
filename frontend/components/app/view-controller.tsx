'use client';

import { useState } from 'react';
import { ConnectionState } from 'livekit-client';
import { useTheme } from 'next-themes';
import { AnimatePresence, motion } from 'motion/react';
import { useSessionContext } from '@livekit/components-react';
import type { AppConfig } from '@/app-config';
import { AgentSessionView_01 } from '@/components/agents-ui/blocks/agent-session-view-01';
import { WelcomeView } from '@/components/app/welcome-view';

const MotionWelcomeView = motion.create(WelcomeView);
const MotionSessionView = motion.create(AgentSessionView_01);

const VIEW_MOTION_PROPS = {
  variants: {
    visible: {
      opacity: 1,
    },
    hidden: {
      opacity: 0,
    },
  },
  initial: 'hidden',
  animate: 'visible',
  exit: 'hidden',
  transition: {
    duration: 0.5,
    ease: 'linear',
  },
};

interface ViewControllerProps {
  appConfig: AppConfig;
}

export function ViewController({ appConfig }: ViewControllerProps) {
  const { isConnected, start, connectionState } = useSessionContext();
  const { resolvedTheme } = useTheme();
  const [hasStartedSession, setHasStartedSession] = useState(false);
  const [connectError, setConnectError] = useState<string | null>(null);
  const [isLaunching, setIsLaunching] = useState(false);

  const isConnecting =
    !isConnected &&
    [ConnectionState.Connecting, ConnectionState.Reconnecting, ConnectionState.SignalReconnecting].includes(
      connectionState
    );
  const showEndedState = hasStartedSession && !isConnected && !isConnecting;

  async function handleStartCall() {
    if (isLaunching || isConnecting) return;

    setConnectError(null);
    setHasStartedSession(true);
    setIsLaunching(true);

    try {
      if (typeof window !== 'undefined' && navigator.mediaDevices?.getUserMedia) {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        stream.getTracks().forEach((track) => track.stop());
      }

      await start();
    } catch (error) {
      const message =
        error instanceof DOMException && error.name === 'NotAllowedError'
          ? 'Microphone access is blocked.'
          : 'Unable to connect. Please check your internet connection and try again.';

      setHasStartedSession(false);
      setConnectError(message);
    } finally {
      setIsLaunching(false);
    }
  }

  return (
    <AnimatePresence mode="wait">
      {isConnected ? (
        <MotionSessionView
          key="session-view"
          {...VIEW_MOTION_PROPS}
          supportsChatInput={appConfig.supportsChatInput}
          supportsVideoInput={appConfig.supportsVideoInput}
          supportsScreenShare={appConfig.supportsScreenShare}
          isPreConnectBufferEnabled={appConfig.isPreConnectBufferEnabled}
          audioVisualizerType={appConfig.audioVisualizerType}
          audioVisualizerColor={
            resolvedTheme === 'dark'
              ? appConfig.audioVisualizerColorDark
              : appConfig.audioVisualizerColor
          }
          audioVisualizerColorShift={appConfig.audioVisualizerColorShift}
          audioVisualizerBarCount={appConfig.audioVisualizerBarCount}
          audioVisualizerGridRowCount={appConfig.audioVisualizerGridRowCount}
          audioVisualizerGridColumnCount={appConfig.audioVisualizerGridColumnCount}
          audioVisualizerRadialBarCount={appConfig.audioVisualizerRadialBarCount}
          audioVisualizerRadialRadius={appConfig.audioVisualizerRadialRadius}
          audioVisualizerWaveLineWidth={appConfig.audioVisualizerWaveLineWidth}
          className="fixed inset-0"
        />
      ) : (
        <MotionWelcomeView
          key={isConnecting ? 'connecting' : showEndedState ? 'ended' : 'welcome'}
          {...VIEW_MOTION_PROPS}
          companyName={appConfig.companyName}
          startButtonText={appConfig.startButtonText}
          mode={isConnecting ? 'connecting' : showEndedState ? 'ended' : 'ready'}
          onStartCall={handleStartCall}
          isBusy={isLaunching || isConnecting}
          errorMessage={connectError}
        />
      )}
    </AnimatePresence>
  );
}
