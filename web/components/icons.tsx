// One icon family: 24px grid, 1.5px stroke, round caps and joins, currentColor.
type IconProps = { className?: string; title?: string };

function Svg({ className, title, children }: IconProps & { children: React.ReactNode }) {
  return (
    <svg
      viewBox="0 0 24 24"
      width="20"
      height="20"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden={title ? undefined : true}
      role={title ? "img" : undefined}
    >
      {title ? <title>{title}</title> : null}
      {children}
    </svg>
  );
}

export const IconMark = (p: IconProps) => (
  <Svg {...p}>
    <path d="M4 18h16" />
    <path d="M6 13h12" />
    <path d="M9 8h6" />
    <circle cx="12" cy="4.5" r="1.5" />
    <path d="M12 6v12" />
  </Svg>
);

export const IconGithub = (p: IconProps) => (
  <Svg {...p}>
    <path d="M9 19c-4 1.3-4-2-6-2.5" />
    <path d="M15 21v-3.4a3 3 0 0 0-.8-2.3c2.7-.3 5.6-1.3 5.6-6a4.7 4.7 0 0 0-1.3-3.2 4.3 4.3 0 0 0-.1-3.2s-1-.3-3.4 1.3a11.6 11.6 0 0 0-6 0C6.6 2.6 5.6 2.9 5.6 2.9a4.3 4.3 0 0 0-.1 3.2 4.7 4.7 0 0 0-1.3 3.2c0 4.7 2.9 5.7 5.6 6a3 3 0 0 0-.8 2.3V21" />
  </Svg>
);

export const IconArrowRight = (p: IconProps) => (
  <Svg {...p}>
    <path d="M5 12h14" />
    <path d="m13 6 6 6-6 6" />
  </Svg>
);

export const IconPlay = (p: IconProps) => (
  <Svg {...p}>
    <path d="M7 5v14l11-7z" />
  </Svg>
);

export const IconPause = (p: IconProps) => (
  <Svg {...p}>
    <path d="M8 5v14" />
    <path d="M16 5v14" />
  </Svg>
);

export const IconStep = (p: IconProps) => (
  <Svg {...p}>
    <path d="M6 5v14l9-7z" />
    <path d="M18 5v14" />
  </Svg>
);

export const IconEnd = (p: IconProps) => (
  <Svg {...p}>
    <path d="m5 6 6 6-6 6" />
    <path d="m12 6 6 6-6 6" />
  </Svg>
);

export const IconReset = (p: IconProps) => (
  <Svg {...p}>
    <path d="M4 12a8 8 0 1 0 2.3-5.7" />
    <path d="M4 4v4h4" />
  </Svg>
);

export const IconShuffle = (p: IconProps) => (
  <Svg {...p}>
    <path d="M4 7h3l10 10h3" />
    <path d="M4 17h3l3-3" />
    <path d="M14 10l3-3h3" />
    <path d="m18 4 2 3-2 3" />
    <path d="m18 14 2 3-2 3" />
  </Svg>
);

export const IconSearch = (p: IconProps) => (
  <Svg {...p}>
    <circle cx="11" cy="11" r="6.5" />
    <path d="m16 16 4 4" />
  </Svg>
);

export const IconExternal = (p: IconProps) => (
  <Svg {...p}>
    <path d="M14 5h5v5" />
    <path d="M19 5 11 13" />
    <path d="M18 14v5H5V6h5" />
  </Svg>
);

export const IconMenu = (p: IconProps) => (
  <Svg {...p}>
    <path d="M4 7h16" />
    <path d="M4 12h16" />
    <path d="M4 17h16" />
  </Svg>
);
