import React, { useState } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import {
  ArrowLeft,
  Compass,
  MapPin,
  Sparkles,
  Layers,
  Building,
  Train,
  CheckCircle2,
  Share2,
} from 'lucide-react';
import { useXRScene, fetchXRScenes } from '../api/xr';
import { XRSceneViewer } from '../components/xr/XRSceneViewer';
import { ARWayfindingPanel } from '../components/xr/ARWayfindingPanel';
import { XRDevicePrompt } from '../components/xr/XRDevicePrompt';
import { useQuery } from '@tanstack/react-query';

export const XRExperiencePage: React.FC = () => {
  const { sceneId } = useParams<{ sceneId: string }>();
  const navigate = useNavigate();
  const [selectedWayfindingId, setSelectedWayfindingId] = useState<string | undefined>();

  const { data: scene, isLoading, error } = useXRScene(sceneId || 'xrs_chennai_central_concourse');
  const { data: allScenes } = useQuery({
    queryKey: ['xr-all-scenes'],
    queryFn: () => fetchXRScenes(),
  });

  if (isLoading) {
    return (
      <div className="max-w-7xl mx-auto px-4 py-16 flex flex-col items-center justify-center min-h-[60vh] gap-4">
        <div className="w-12 h-12 rounded-full border-4 border-blue-600 border-t-transparent animate-spin" />
        <p className="text-slate-600 font-medium text-sm">Loading 360° Spatial Scene...</p>
      </div>
    );
  }

  if (error || !scene) {
    return (
      <div className="max-w-7xl mx-auto px-4 py-16 flex flex-col items-center justify-center min-h-[60vh] gap-4 text-center">
        <div className="p-4 rounded-2xl bg-rose-50 text-rose-600 border border-rose-200">
          <Compass className="w-8 h-8" />
        </div>
        <h2 className="text-xl font-bold text-slate-900">Spatial Scene Not Found</h2>
        <p className="text-sm text-slate-500 max-w-md">
          The requested XR experience could not be loaded. Please return to your journey itinerary.
        </p>
        <button
          type="button"
          onClick={() => navigate(-1)}
          className="px-4 py-2 rounded-xl bg-blue-600 text-white font-semibold text-sm shadow-sm hover:bg-blue-500 transition-colors"
        >
          Return to Itinerary
        </button>
      </div>
    );
  }

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 w-full flex flex-col gap-6 min-w-0 max-w-full">
      {/* Top Header Card */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 p-4 sm:p-5 rounded-2xl border border-slate-200 bg-white shadow-xs">
        <div className="flex items-center gap-3.5">
          <button
            type="button"
            onClick={() => navigate(-1)}
            className="p-2.5 rounded-xl bg-slate-100 hover:bg-slate-200 text-slate-700 transition-colors shrink-0 shadow-2xs"
            title="Back to Previous View"
          >
            <ArrowLeft className="w-4 h-4" />
          </button>
          <div className="flex flex-col">
            <div className="flex flex-wrap items-center gap-2">
              <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full bg-blue-50 border border-blue-200 text-blue-700 font-mono text-[11px] font-bold uppercase tracking-wider">
                <Sparkles className="w-3 h-3 text-blue-500" />
                {scene.entity_type === 'hotel' ? 'Hotel XR Preview' : 'Intermodal Transfer Hub'}
              </span>
              <span className="text-xs text-slate-400 font-mono">·</span>
              <span className="text-xs font-semibold text-slate-600 flex items-center gap-1">
                <MapPin className="w-3.5 h-3.5 text-slate-400" />
                {scene.city_name}
              </span>
            </div>
            <h1 className="text-lg sm:text-2xl font-extrabold text-slate-950 font-display mt-0.5">
              {scene.title}
            </h1>
          </div>
        </div>

        {/* Scene Meta Badges */}
        <div className="flex items-center gap-2 shrink-0">
          <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-slate-100 text-slate-700 font-mono text-xs font-semibold border border-slate-200">
            <Compass className="w-3.5 h-3.5 text-slate-500" />
            360° Spherical View
          </span>
          {scene.wayfinding_cases.length > 0 && (
            <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-emerald-50 text-emerald-800 font-mono text-xs font-semibold border border-emerald-200">
              <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />
              {scene.wayfinding_cases.length} AR Wayfinding Routes
            </span>
          )}
        </div>
      </div>

      {/* Main 360 Spatial Canvas Viewer */}
      <div className="w-full flex flex-col gap-3">
        <XRSceneViewer
          scene={scene}
          onSelectWayfinding={(wid) => setSelectedWayfindingId(wid)}
        />
        {/* Device capability prompt */}
        <XRDevicePrompt />
      </div>

      {/* AR Wayfinding Guidance Section */}
      {scene.wayfinding_cases && scene.wayfinding_cases.length > 0 && (
        <ARWayfindingPanel
          wayfindingCases={scene.wayfinding_cases}
          selectedCaseId={selectedWayfindingId}
          onSelectCase={(wid) => setSelectedWayfindingId(wid)}
        />
      )}

      {/* Scene Overview & Location Details Card */}
      <div className="p-5 rounded-2xl border border-slate-200 bg-white shadow-xs flex flex-col gap-3">
        <h3 className="text-base font-bold text-slate-950 flex items-center gap-2">
          <Layers className="w-4 h-4 text-blue-600" />
          <span>About this Location</span>
        </h3>
        <p className="text-sm text-slate-600 leading-relaxed">{scene.description}</p>
        <div className="flex flex-wrap items-center gap-2 pt-2 border-t border-slate-100">
          <span className="text-xs text-slate-500 font-semibold">Location:</span>
          <span className="text-xs font-bold text-slate-800 bg-slate-100 px-2.5 py-1 rounded-lg">
            {scene.location_name}
          </span>
          <span className="text-xs text-slate-400">·</span>
          <span className="text-xs text-slate-500 font-semibold">Scene ID:</span>
          <span className="text-xs font-mono text-blue-700 bg-blue-50 px-2 py-0.5 rounded-md">
            {scene.scene_id}
          </span>
        </div>
      </div>

      {/* Other Explore Scenes Switcher */}
      {allScenes && allScenes.length > 1 && (
        <div className="flex flex-col gap-3 pt-2">
          <h4 className="text-xs font-bold uppercase tracking-wider text-slate-500 font-mono">
            Explore Other Journey Hubs in 360°
          </h4>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {allScenes
              .filter((s) => s.scene_id !== scene.scene_id)
              .map((s) => (
                <Link
                  key={s.scene_id}
                  to={`/xr/${s.scene_id}`}
                  className="p-3.5 rounded-xl border border-slate-200 bg-white hover:border-blue-400 hover:shadow-sm transition-all flex items-center gap-3 group"
                >
                  <div className="p-2 rounded-lg bg-blue-50 text-blue-600 group-hover:bg-blue-600 group-hover:text-white transition-colors">
                    {s.entity_type === 'hotel' ? (
                      <Building className="w-4 h-4" />
                    ) : (
                      <Train className="w-4 h-4" />
                    )}
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="text-xs font-bold text-slate-900 group-hover:text-blue-600 truncate transition-colors">
                      {s.title}
                    </div>
                    <div className="text-[11px] text-slate-500 truncate">{s.location_name}</div>
                  </div>
                </Link>
              ))}
          </div>
        </div>
      )}
    </div>
  );
};
