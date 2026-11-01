import React, { useState } from 'react';
import { Compass } from 'lucide-react';
import { ExploreImageConfig } from '../../data/exploreImages';

interface ResponsiveImageProps {
  image: ExploreImageConfig;
  sizes?: string;
  className?: string;
  priority?: boolean;
  aspectRatioClass?: string;
}

export const ResponsiveImage: React.FC<ResponsiveImageProps> = ({
  image,
  sizes = '(max-width: 768px) 100vw, (max-width: 1200px) 50vw, 33vw',
  className = '',
  priority = false,
  aspectRatioClass = 'aspect-[16/10]',
}) => {
  const [hasError, setHasError] = useState(false);
  const [isLoaded, setIsLoaded] = useState(false);

  if (hasError) {
    return (
      <div
        className={`w-full ${aspectRatioClass} bg-gradient-to-br from-slate-100 to-blue-50/60 flex flex-col items-center justify-center text-slate-400 p-4 border border-slate-200/60`}
      >
        <Compass className="w-8 h-8 text-[#1769FF]/50 animate-pulse mb-2" />
        <span className="text-xs font-semibold text-slate-600 tracking-wide text-center line-clamp-1">
          {image.alt || 'KogniSync Destination'}
        </span>
      </div>
    );
  }

  return (
    <div className={`relative w-full overflow-hidden bg-slate-100 ${aspectRatioClass}`}>
      <img
        src={image.src}
        srcSet={image.srcSet}
        sizes={sizes}
        alt={image.alt}
        width={image.width}
        height={image.height}
        loading={priority ? 'eager' : 'lazy'}
        decoding={priority ? 'sync' : 'async'}
        // @ts-expect-error fetchpriority is standard in modern HTML
        fetchpriority={priority ? 'high' : 'low'}
        onError={() => setHasError(true)}
        onLoad={() => setIsLoaded(true)}
        style={{
          objectPosition: image.objectPosition || 'center center',
        }}
        className={`w-full h-full object-cover transition-all duration-700 ${
          isLoaded ? 'opacity-100' : 'opacity-0 scale-[1.02]'
        } ${className}`}
      />
      {!isLoaded && (
        <div className="absolute inset-0 bg-slate-200/60 animate-pulse pointer-events-none" />
      )}
    </div>
  );
};

export default ResponsiveImage;

