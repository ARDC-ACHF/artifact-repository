function ChipGroup({ title, options, selected, onChange, colourBy }) {
  const allSelected = selected.length === 0;
  return (
    <div className="chip-group" role="group" aria-label={title}>
      <span className="chip-group__title">{title}</span>
      <button type="button" className={`chip${allSelected ? ' chip--on' : ''}`} aria-pressed={allSelected} onClick={() => onChange([])}>
        All
      </button>
      {options.map((option) => {
        const on = selected.includes(option.slug);
        const colour = colourBy ? ` partner-${option.slug}` : '';
        return (
          <button
            key={option.slug}
            type="button"
            className={`chip${colour}${on ? ' chip--on' : ''}`}
            aria-pressed={on}
            title={option.blurb}
            onClick={() => onChange(on ? selected.filter((v) => v !== option.slug) : [...selected, option.slug])}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}

export default function FilterChips({ partners, types, partnerOptions, typeOptions, onPartnersChange, onTypesChange }) {
  return (
    <div className="filters">
      <ChipGroup title="Partner" options={partnerOptions} selected={partners} onChange={onPartnersChange} colourBy />
      <ChipGroup title="Type" options={typeOptions} selected={types} onChange={onTypesChange} />
    </div>
  );
}
