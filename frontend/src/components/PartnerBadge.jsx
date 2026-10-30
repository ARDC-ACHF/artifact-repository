import { isKnownPartner, partnerLabel } from '../lib/filters.js';

export default function PartnerBadge({ partner }) {
  const cls = isKnownPartner(partner) ? `partner-${partner}` : 'partner-other';
  return <span className={`partner-badge ${cls}`}>{partnerLabel(partner)}</span>;
}
