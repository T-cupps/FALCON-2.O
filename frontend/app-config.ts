export interface AppConfig {
  pageTitle: string;
  pageDescription: string;
  companyName: string;

  supportsChatInput: boolean;
  supportsVideoInput: boolean;
  supportsScreenShare: boolean;
  isPreConnectBufferEnabled: boolean;

  logo: string;
  startButtonText: string;
  accent?: string;
  logoDark?: string;
  accentDark?: string;

  audioVisualizerType?: 'bar' | 'wave' | 'grid' | 'radial' | 'aura';
  audioVisualizerColor?: `#${string}`;
  audioVisualizerColorDark?: `#${string}`;
  audioVisualizerColorShift?: number;
  audioVisualizerBarCount?: number;
  audioVisualizerGridRowCount?: number;
  audioVisualizerGridColumnCount?: number;
  audioVisualizerRadialBarCount?: number;
  audioVisualizerRadialRadius?: number;
  audioVisualizerWaveLineWidth?: number;

  // agent dispatch configuration
  agentName?: string;

  // LiveKit Cloud Sandbox configuration
  sandboxId?: string;
}

export const APP_CONFIG_DEFAULTS: AppConfig = {
  companyName: 'AI Learning Assistant',

  pageTitle: 'AI Learning Assistant',

  pageDescription:
    'Learn, practice, and explore with your voice-powered learning companion.',

  supportsChatInput: true,

  supportsVideoInput: true,

  supportsScreenShare: true,

  isPreConnectBufferEnabled: true,

  logo: '/murf-logo.svg',

  // Learning & Literacy theme
  accent: '#0F9D78',

  logoDark: '/murf-logo-dark.svg',

  accentDark: '#4FD1A5',

  startButtonText: 'Start Learning',

  // Educational voice visualization
  audioVisualizerType: 'aura',

  audioVisualizerColor: '#0F9D78',

  audioVisualizerColorDark: '#4FD1A5',

  audioVisualizerColorShift: 0.35,

  audioVisualizerBarCount: 8,

  // Optional visualizer configurations
  // audioVisualizerType: 'radial',
  // audioVisualizerRadialBarCount: 24,
  // audioVisualizerRadialRadius: 100,

  // audioVisualizerType: 'grid',
  // audioVisualizerGridRowCount: 25,
  // audioVisualizerGridColumnCount: 25,

  // audioVisualizerType: 'wave',
  // audioVisualizerWaveLineWidth: 3,

  // Agent dispatch configuration
  agentName: process.env.AGENT_NAME ?? undefined,

  // LiveKit Cloud Sandbox configuration
  sandboxId: undefined,
};
