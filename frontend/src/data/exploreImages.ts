export interface ExploreImageConfig {
  src: string;
  srcSet?: string;
  alt: string;
  width: number;
  height: number;
  objectPosition?: string;
}

export function buildUnsplashSrcSet(baseUrl: string): string {
  return `${baseUrl}?w=600&auto=format&fit=crop&q=80 600w, ${baseUrl}?w=1000&auto=format&fit=crop&q=85 1000w, ${baseUrl}?w=1400&auto=format&fit=crop&q=85 1400w, ${baseUrl}?w=1800&auto=format&fit=crop&q=90 1800w`;
}

export const exploreImages = {
  hero: {
    src: '/images/explore/explore-hero.jpg',
    srcSet: buildUnsplashSrcSet('https://images.unsplash.com/photo-1507525428034-b723cf961d3e'),
    alt: 'Scenic tropical coastline and golden beach at warm sunset',
    width: 1920,
    height: 1276,
    objectPosition: 'center 35%',
  },
  destinations: {
    coorg: {
      src: '/images/explore/coorg.jpg',
      srcSet: buildUnsplashSrcSet('https://images.unsplash.com/photo-1588668214407-6ea9a6d8c272'),
      alt: 'Misty green hills and coffee valleys of Coorg, Western Ghats',
      width: 1200,
      height: 800,
      objectPosition: 'center center',
    },
    mysore: {
      src: '/images/explore/mysore.jpg',
      srcSet: buildUnsplashSrcSet('https://images.unsplash.com/photo-1590766940554-634a7ed41450'),
      alt: 'Grand illuminated Mysore Palace architecture under dramatic twilight',
      width: 1200,
      height: 697,
      objectPosition: 'center 40%',
    },
    goa: {
      src: '/images/explore/goa-popular.jpg',
      srcSet: buildUnsplashSrcSet('https://images.unsplash.com/photo-1512343879784-a960bf40e7f2'),
      alt: 'Goan tropical coastline with swaying palm trees and calm sea waves',
      width: 1200,
      height: 900,
      objectPosition: 'center center',
    },
    chennai: {
      src: '/images/explore/chennai-popular.jpg',
      srcSet: buildUnsplashSrcSet('https://images.unsplash.com/photo-1582510003544-4d00b7f74220'),
      alt: 'Historic Dravidian temple gopuram architecture with detailed stonework in Chennai',
      width: 1200,
      height: 800,
      objectPosition: 'center 30%',
    },
  },
  curated: {
    weekendEscape: {
      src: '/images/explore/curated-bus.jpg',
      srcSet: buildUnsplashSrcSet('https://images.unsplash.com/photo-1570125909232-eb263c188f7e'),
      alt: 'Modern intercity travel coach on scenic highway to the hills',
      width: 1200,
      height: 800,
      objectPosition: 'center 60%',
    },
    fastEscape: {
      src: '/images/explore/curated-flight.jpg',
      srcSet: buildUnsplashSrcSet('https://images.unsplash.com/photo-1436491865332-7a61a109cc05'),
      alt: 'Commercial flight soaring through golden coastal evening sky',
      width: 1200,
      height: 797,
      objectPosition: 'center 45%',
    },
    scenicRoute: {
      src: '/images/explore/curated-train.jpg',
      srcSet: buildUnsplashSrcSet('https://images.unsplash.com/photo-1541872703-74c5e44368f9'),
      alt: 'Panoramic rail journey through lush green valleys and bridges',
      width: 1200,
      height: 864,
      objectPosition: 'center center',
    },
  },
  moods: {
    beaches: {
      src: '/images/explore/mood-beach.jpg',
      srcSet: buildUnsplashSrcSet('https://images.unsplash.com/photo-1507525428034-b723cf961d3e'),
      alt: 'Sunlit turquoise beach escape with palm trees',
      width: 800,
      height: 532,
      objectPosition: 'center center',
    },
    mountains: {
      src: '/images/explore/mood-mountains.jpg',
      srcSet: buildUnsplashSrcSet('https://images.unsplash.com/photo-1464822759023-fed622ff2c3b'),
      alt: 'Breathtaking misty mountain range overlooking morning clouds',
      width: 800,
      height: 533,
      objectPosition: 'center 35%',
    },
    heritage: {
      src: '/images/explore/mood-heritage.jpg',
      srcSet: buildUnsplashSrcSet('https://images.unsplash.com/photo-1608958435020-e8a7109ba809'),
      alt: 'Historic Indian stone temple architecture and carved pillars',
      width: 800,
      height: 450,
      objectPosition: 'center 40%',
    },
    nature: {
      src: '/images/explore/mood-nature.jpg',
      srcSet: buildUnsplashSrcSet('https://images.unsplash.com/photo-1441974231531-c6227db76b6e'),
      alt: 'Serene sun-dappled forest canopy and pristine nature retreat',
      width: 800,
      height: 533,
      objectPosition: 'center center',
    },
    adventure: {
      src: '/images/explore/mood-adventure.jpg',
      srcSet: buildUnsplashSrcSet('https://images.unsplash.com/photo-1501555088652-021faa106b9b'),
      alt: 'Mountain ridge trekker enjoying vast panoramic wilderness',
      width: 800,
      height: 532,
      objectPosition: 'center 25%',
    },
    foodCulture: {
      src: '/images/explore/mood-food.jpg',
      srcSet: buildUnsplashSrcSet('https://images.unsplash.com/photo-1555396273-367ea4eb4db5'),
      alt: 'Vibrant evening market and cultural food street life',
      width: 800,
      height: 600,
      objectPosition: 'center 40%',
    },
  },
  featured: {
    goa: {
      src: '/images/explore/featured-goa.jpg',
      srcSet: buildUnsplashSrcSet('https://images.unsplash.com/photo-1512343879784-a960bf40e7f2'),
      alt: 'Panoramic Goa coastal landscape with tranquil waters and sunset warmth',
      width: 1920,
      height: 1440,
      objectPosition: 'center 50%',
    },
  },
} as const;

