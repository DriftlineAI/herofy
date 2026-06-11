import React from 'react';
import { Link } from 'react-router-dom';
import { cn } from '@/lib/utils';

interface StarterTileProps {
  title: string;
  subtitle: string;
  eyebrow?: string;
  cta: string;
  to: string;
  featured?: boolean;
  className?: string;
}

/**
 * StarterTile - Featured entry point cards
 * Used in PlaybookStart (Artboard 2)
 * Featured variant gets 2px rust left-border and rust accents
 */
export function StarterTile({
  title,
  subtitle,
  eyebrow,
  cta,
  to,
  featured,
  className
}: StarterTileProps) {
  // Replace "Sidekick" with italic rust variant
  const renderTitle = () => {
    const parts = title.split('Sidekick');
    if (parts.length === 1) return title;

    return (
      <>
        {parts[0]}
        <em className="text-rust-500 not-italic font-serif">Sidekick</em>
        {parts[1]}
      </>
    );
  };

  return (
    <Link
      to={to}
      className={cn(
        'pb-start__tile',
        featured && 'pb-start__tile--featured',
        className
      )}
    >
      {eyebrow && (
        <div className="pb-start__tile-eyebrow">{eyebrow}</div>
      )}
      <h3 className="pb-start__tile-title">{renderTitle()}</h3>
      <p className="pb-start__tile-sub">{subtitle}</p>
      <div className="pb-start__tile-cta">{cta}</div>
    </Link>
  );
}
