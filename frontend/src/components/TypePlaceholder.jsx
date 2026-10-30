// Illustrated fallback shown when a record has no image or its image fails to load.

const ICONS = {
  event: (
    <g>
      <path d="M14 40c0-10 8-18 18-18s18 8 18 18" />
      <path d="M10 22c6-6 14-9 22-9s16 3 22 9" />
      <path d="M22 40v8M42 40v8M18 48h28" />
      <circle cx="32" cy="34" r="3" />
    </g>
  ),
  person: (
    <g>
      <circle cx="32" cy="22" r="9" />
      <path d="M14 50c2-10 9-16 18-16s16 6 18 16" />
    </g>
  ),
  place: (
    <g>
      <path d="M32 52s-14-14-14-25a14 14 0 0 1 28 0c0 11-14 25-14 25Z" />
      <circle cx="32" cy="27" r="5" />
    </g>
  ),
  object: (
    <g>
      <rect x="12" y="14" width="40" height="36" rx="2" />
      <rect x="18" y="20" width="28" height="24" />
      <path d="m18 40 9-9 6 6 4-4 9 7" />
      <circle cx="39" cy="27" r="2.5" />
    </g>
  ),
  text: (
    <g>
      <path d="M18 12h20l8 8v32H18Z" />
      <path d="M38 12v8h8M24 30h16M24 37h16M24 44h10" />
    </g>
  ),
  other: (
    <g>
      <circle cx="32" cy="32" r="18" />
      <path d="M32 22v12M32 40v2" />
    </g>
  ),
};

export default function TypePlaceholder({ kind = 'other', label, compact = false }) {
  const icon = ICONS[kind] || ICONS.other;
  return (
    <div className={`type-placeholder type-placeholder--${kind}${compact ? ' type-placeholder--compact' : ''}`} role="img" aria-label={label ? `No image for ${label}` : 'No image available'}>
      <svg viewBox="0 0 64 64" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        {icon}
      </svg>
    </div>
  );
}
