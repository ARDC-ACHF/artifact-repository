import { useState } from 'react';

import { parseCredit } from '../lib/links.js';
import TypePlaceholder from './TypePlaceholder.jsx';

function Credit({ image }) {
  const credit = parseCredit(image.credit, image.url);
  return (
    <p className="gallery__credit">
      <span className="gallery__credit-label">Image:</span>{' '}
      {credit.text || 'Credit not recorded'}
      {credit.licence && !credit.text.includes(credit.licence) && <> · {credit.licence}</>}
      {credit.sourceUrl && (
        <>
          {' · '}
          <a href={credit.sourceUrl} target="_blank" rel="noopener noreferrer">{credit.sourceLabel}</a>
        </>
      )}
    </p>
  );
}

/** Hero image with thumbnails; broken images are skipped and the type placeholder is the last resort. */
export default function ImageGallery({ images, kind, label }) {
  const [failed, setFailed] = useState(() => new Set());
  const [selected, setSelected] = useState(null);
  const usable = images.filter((img) => !failed.has(img.url));
  const current = usable.find((img) => img.url === selected) || usable[0];

  if (!current) {
    return (
      <figure className="gallery gallery--empty">
        <div className="gallery__stage"><TypePlaceholder kind={kind} label={label} /></div>
        <figcaption className="gallery__credit">
          {images.length ? 'The image for this record could not be loaded.' : 'No image is available for this record.'}
        </figcaption>
      </figure>
    );
  }

  return (
    <figure className="gallery">
      <div className="gallery__stage">
        <img
          key={current.url}
          src={current.url}
          alt={current.label || label}
          decoding="async"
          onError={() => setFailed((prev) => new Set(prev).add(current.url))}
        />
      </div>
      {usable.length > 1 && (
        <div className="gallery__thumbs" role="group" aria-label="Choose image">
          {usable.map((img, i) => (
            <button
              key={img.url}
              type="button"
              className={`gallery__thumb${img === current ? ' gallery__thumb--on' : ''}`}
              aria-pressed={img === current}
              aria-label={`Image ${i + 1}${img.label ? `: ${img.label}` : ''}`}
              onClick={() => setSelected(img.url)}
            >
              <img src={img.url} alt="" loading="lazy" onError={() => setFailed((prev) => new Set(prev).add(img.url))} />
            </button>
          ))}
        </div>
      )}
      <figcaption>
        {current.label && current.label !== label && <p className="gallery__caption">{current.label}</p>}
        <Credit image={current} />
      </figcaption>
    </figure>
  );
}
