import { BadgeKind } from '../components/badges';

export interface VerifyBadgeResult {
  hasBadges: boolean;
  badges: BadgeKind[];
  valid: boolean;
}

/**
 * Inline verification assertion ensuring every rendered number carries at least one badge.
 * Per FE_DESIGN.md §0 rule #1 & API_CONTRACT.md §0 rule #2.
 */
export function verifyValueBadge(item: { value?: any; badges?: BadgeKind[] }): VerifyBadgeResult {
  const badges = item.badges || [];
  const hasBadges = Array.isArray(badges) && badges.length > 0;
  const validKinds: BadgeKind[] = ['LIVE', 'FORECAST', 'SIMULATED', 'BASELINE'];
  const valid = hasBadges && badges.every((b) => validKinds.includes(b));

  if (!valid) {
    console.error('[Verification Failed] Value rendered without a valid provenance badge:', item);
  }

  return { hasBadges, badges, valid };
}

