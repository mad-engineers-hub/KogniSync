import React from 'react';
import { Journey } from '../../types/journey';
import { TransportSegment } from './TransportSegment';
import { Clock } from 'lucide-react';

interface JourneyTimelineProps {
  journey: Journey;
}

export const JourneyTimeline: React.FC<JourneyTimelineProps> = ({ journey }) => {
  return (
    <div className="w-full flex flex-col gap-4">
      <div className="flex items-center justify-between border-b border-slate-200 pb-3">
        <h3 className="text-sm font-bold uppercase tracking-wider text-slate-900 font-display">
          Synchronized Transit Timeline
        </h3>
        <span className="text-xs font-mono text-slate-500 font-medium">
          {journey.segments.length} Leg{journey.segments.length > 1 ? 's' : ''} ·{' '}
          {journey.totalTransfers} Transfer{journey.totalTransfers !== 1 ? 's' : ''}
        </span>
      </div>

      <div className="flex flex-col gap-4 relative">
        {journey.segments.map((segment, index) => {
          const nextSeg = journey.segments[index + 1];
          const transferBuffer = segment.transferBufferMinutes || 15;

          return (
            <React.Fragment key={segment.segmentId}>
              <TransportSegment
                segment={segment}
                index={index}
                totalSegments={journey.segments.length}
              />

              {/* Synchronized Intermodal Transfer Node */}
              {nextSeg && (
                <div className="flex flex-col items-center justify-center my-1 relative">
                  <div className="w-0.5 h-5 bg-amber-300" />
                  <div className="flex items-center gap-2 px-3 sm:px-4 py-2 rounded-xl bg-amber-50 border border-amber-200/90 text-xs text-amber-950 font-mono shadow-2xs max-w-full min-w-0 flex-wrap">
                    <Clock className="w-3.5 h-3.5 text-amber-600 shrink-0" />
                    <span className="truncate">
                      <strong className="font-bold text-amber-900">{transferBuffer} min transfer</strong>
                      <span className="text-amber-400 mx-2">·</span>
                      Change at <strong className="font-bold text-slate-900">{segment.destination.name}</strong>
                    </span>
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
