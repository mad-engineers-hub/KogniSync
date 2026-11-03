import React from 'react';
import { Link } from 'react-router-dom';
import { Clock, Compass, Eye, Sparkles } from 'lucide-react';
import { Journey } from '../../types/journey';
import { TransportSegment } from './TransportSegment';
import { matchXRSceneForHub } from '../../utils/xrMatching';

interface JourneyTimelineProps {
  journey: Journey;
}

export const JourneyTimeline: React.FC<JourneyTimelineProps> = ({ journey }) => {
  return (
    <div className="w-full flex flex-col gap-6">
      <div className="flex items-center justify-between border-b border-slate-200 pb-3">
        <h2 className="text-lg font-bold text-slate-900 font-display">
          Multi-Modal Journey Itinerary
        </h2>
        <span className="text-xs font-mono font-medium text-slate-500">
          {journey.segments.length} Ordered Segments · {journey.totalTransfers} Transfers
        </span>
      </div>

      <div className="flex flex-col gap-3 relative">
        {journey.segments.map((segment, index) => {
          const nextSeg = journey.segments[index + 1];
          const transferBuffer = segment.transferBufferMinutes || 15;
          const transferSceneId = nextSeg ? matchXRSceneForHub(segment.destination.name) : null;

          return (
            <React.Fragment key={segment.segmentId || index}>
              <TransportSegment
                segment={segment}
                index={index}
                totalSegments={journey.segments.length}
              />

              {/* Synchronized Intermodal Transfer Node */}
              {nextSeg && (
                <div className="flex flex-col items-center justify-center my-1 relative">
                  <div className="w-0.5 h-5 bg-amber-300" />
                  <div className="flex flex-wrap items-center justify-between gap-3 px-3 sm:px-4 py-2.5 rounded-xl bg-amber-50 border border-amber-200/90 text-xs text-amber-950 font-mono shadow-2xs max-w-full min-w-0 w-full sm:w-auto">
                    <div className="flex items-center gap-2 min-w-0">
                      <Clock className="w-3.5 h-3.5 text-amber-600 shrink-0" />
                      <span className="truncate">
                        <strong className="font-bold text-amber-900">{transferBuffer} min transfer</strong>
                        <span className="text-amber-400 mx-2">·</span>
                        Change at <strong className="font-bold text-slate-900">{segment.destination.name}</strong>
                      </span>
                    </div>

                    {transferSceneId && (
                      <Link
                        to={`/xr/${transferSceneId}`}
                        className="inline-flex items-center gap-1.5 px-3 py-1 rounded-lg bg-blue-600 hover:bg-blue-700 text-white font-sans text-xs font-semibold shadow-xs transition-colors shrink-0"
                        title="View 360° Station Guide & AR Wayfinding"
                      >
                        <Compass className="w-3.5 h-3.5 animate-spin-slow" />
                        <span>360° Station Guide & AR Wayfinding</span>
                      </Link>
                    )}
                  </div>
                  <div className="w-0.5 h-5 bg-amber-300" />
                </div>
              )}
            </React.Fragment>
          );
        })}
      </div>
    </div>
  );
};

export default JourneyTimeline;
