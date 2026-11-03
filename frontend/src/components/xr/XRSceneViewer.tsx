import React, { useEffect, useRef, useState, useCallback } from 'react';
import {
  Compass,
  Maximize2,
  Minimize2,
  ZoomIn,
  ZoomOut,
  RotateCcw,
  Sparkles,
  MapPin,
  Layers,
  Eye,
  Camera,
} from 'lucide-react';
import { XRScene, XRSceneHotspot } from '../../types/xr';
import { XRHotspotOverlay } from './XRHotspotOverlay';

interface XRSceneViewerProps {
  scene: XRScene;
  onSelectWayfinding?: (wayfindingId: string) => void;
}

export const XRSceneViewer: React.FC<XRSceneViewerProps> = ({ scene, onSelectWayfinding }) => {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);

  // View state
  const [yaw, setYaw] = useState<number>(180); // 0 to 360 deg
  const [pitch, setPitch] = useState<number>(0); // -85 to +85 deg
  const [fov, setFov] = useState<number>(75); // Field of view in degrees
  const [isDragging, setIsDragging] = useState<boolean>(false);
  const [dragStart, setDragStart] = useState<{ x: number; y: number }>({ x: 0, y: 0 });
  const [isFullscreen, setIsFullscreen] = useState<boolean>(false);
  const [activeHotspot, setActiveHotspot] = useState<XRSceneHotspot | null>(null);
  const [imageLoaded, setImageLoaded] = useState<boolean>(false);
  const [isARSimulated, setIsARSimulated] = useState<boolean>(false);

  // Loaded image ref
  const imageRef = useRef<HTMLImageElement | null>(null);

  // Determine asset URI
  const primaryAsset =
    scene.assets.find((a) => a.format === 'jpg_equirect') || scene.assets[0];
  const imageUri = primaryAsset?.uri;

  // Preload image
  useEffect(() => {
    setImageLoaded(false);
    if (!imageUri) return;

    const img = new Image();
    img.crossOrigin = 'anonymous';
    img.src = imageUri;
    img.onload = () => {
      imageRef.current = img;
      setImageLoaded(true);
    };
    img.onerror = () => {
      // Fallback: procedural rendering if image network fails
      setImageLoaded(true);
    };
  }, [imageUri]);

  // Handle Fullscreen toggle
  const toggleFullscreen = () => {
    if (!containerRef.current) return;
    if (!document.fullscreenElement) {
      containerRef.current.requestFullscreen().then(() => setIsFullscreen(true)).catch(() => {});
    } else {
      document.exitFullscreen().then(() => setIsFullscreen(false)).catch(() => {});
    }
  };

  // Canvas Equirectangular Projection Renderer
  const renderPanorama = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const width = canvas.width;
    const height = canvas.height;

    // Clear
    ctx.clearRect(0, 0, width, height);

    if (imageRef.current && imageRef.current.complete && imageRef.current.naturalWidth > 0) {
      const img = imageRef.current;
      // Calculate equirectangular crop mapping
      // Center yaw is at normalized x offset
      const normYaw = ((yaw % 360) + 360) % 360 / 360; // 0..1
      const normPitch = Math.max(-85, Math.min(85, pitch)) / 180; // -0.47..+0.47

      const srcWidth = img.naturalWidth * (fov / 360);
      const srcHeight = img.naturalHeight * (fov / 180);

      const srcX = normYaw * img.naturalWidth - srcWidth / 2;
      const srcY = (0.5 - normPitch) * img.naturalHeight - srcHeight / 2;

      // Handle horizontal wrapping seamlessly
      if (srcX < 0) {
        const wrapPart = Math.abs(srcX);
        ctx.drawImage(
          img,
          img.naturalWidth - wrapPart,
          Math.max(0, srcY),
          wrapPart,
          srcHeight,
          0,
          0,
          (wrapPart / srcWidth) * width,
          height
        );
        ctx.drawImage(
          img,
          0,
          Math.max(0, srcY),
          srcWidth - wrapPart,
          srcHeight,
          (wrapPart / srcWidth) * width,
          0,
          width - (wrapPart / srcWidth) * width,
          height
        );
      } else if (srcX + srcWidth > img.naturalWidth) {
        const directPart = img.naturalWidth - srcX;
        ctx.drawImage(
          img,
          srcX,
          Math.max(0, srcY),
          directPart,
          srcHeight,
          0,
          0,
          (directPart / srcWidth) * width,
          height
        );
        ctx.drawImage(
          img,
          0,
          Math.max(0, srcY),
          srcWidth - directPart,
          srcHeight,
          (directPart / srcWidth) * width,
          0,
          width - (directPart / srcWidth) * width,
          height
        );
      } else {
        ctx.drawImage(img, srcX, Math.max(0, srcY), srcWidth, srcHeight, 0, 0, width, height);
      }
    } else {
      // Procedural modern cyber/station grid fallback
      const grad = ctx.createLinearGradient(0, 0, 0, height);
      grad.addColorStop(0, '#020617');
      grad.addColorStop(0.5, '#0f172a');
      grad.addColorStop(1, '#1e293b');
      ctx.fillStyle = grad;
      ctx.fillRect(0, 0, width, height);

      // Grid lines indicating spherical floor
      ctx.strokeStyle = 'rgba(56, 189, 248, 0.2)';
      ctx.lineWidth = 1;
      for (let i = 0; i < width; i += 40) {
        ctx.beginPath();
        ctx.moveTo(i, 0);
        ctx.lineTo(i, height);
        ctx.stroke();
      }
      for (let j = 0; j < height; j += 40) {
        ctx.beginPath();
        ctx.moveTo(0, j);
        ctx.lineTo(width, j);
        ctx.stroke();
      }

      ctx.fillStyle = '#94a3b8';
      ctx.font = '14px sans-serif';
      ctx.textAlign = 'center';
      ctx.fillText(scene.title, width / 2, height / 2 - 20);
      ctx.font = '11px monospace';
      ctx.fillText('Interactive 360° Concourse Spatial Matrix', width / 2, height / 2 + 10);
    }

    // AR Passthrough simulation grid overlay
    if (isARSimulated) {
      ctx.strokeStyle = 'rgba(16, 185, 129, 0.35)';
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      ctx.arc(width / 2, height / 2, 40, 0, Math.PI * 2);
      ctx.stroke();
      ctx.strokeRect(width / 2 - 120, height / 2 - 80, 240, 160);
    }
  }, [yaw, pitch, fov, scene, isARSimulated]);

  // Resize canvas to match display resolution
  useEffect(() => {
    const handleResize = () => {
      const canvas = canvasRef.current;
      const container = containerRef.current;
      if (!canvas || !container) return;
      canvas.width = container.clientWidth * (window.devicePixelRatio || 1);
      canvas.height = container.clientHeight * (window.devicePixelRatio || 1);
      renderPanorama();
    };

    handleResize();
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, [renderPanorama]);

  // Re-render when view changes
  useEffect(() => {
    renderPanorama();
  }, [renderPanorama]);

  // Mouse & Touch Pan controls
  const handleMouseDown = (e: React.MouseEvent) => {
    setIsDragging(true);
    setDragStart({ x: e.clientX, y: e.clientY });
  };

  const handleMouseMove = (e: React.MouseEvent) => {
    if (!isDragging) return;
    const dx = e.clientX - dragStart.x;
    const dy = e.clientY - dragStart.y;
    setDragStart({ x: e.clientX, y: e.clientY });

    const sensitivity = (fov / 75) * 0.3;
    setYaw((prev) => (prev - dx * sensitivity + 360) % 360);
    setPitch((prev) => Math.max(-80, Math.min(80, prev + dy * sensitivity)));
  };

  const handleMouseUp = () => setIsDragging(false);

  const handleTouchStart = (e: React.TouchEvent) => {
    if (e.touches.length === 1) {
      setIsDragging(true);
      setDragStart({ x: e.touches[0].clientX, y: e.touches[0].clientY });
    }
  };

  const handleTouchMove = (e: React.TouchEvent) => {
    if (!isDragging || e.touches.length !== 1) return;
    const dx = e.touches[0].clientX - dragStart.x;
    const dy = e.touches[0].clientY - dragStart.y;
    setDragStart({ x: e.touches[0].clientX, y: e.touches[0].clientY });

    const sensitivity = (fov / 75) * 0.35;
    setYaw((prev) => (prev - dx * sensitivity + 360) % 360);
    setPitch((prev) => Math.max(-80, Math.min(80, prev + dy * sensitivity)));
  };

  const handleTouchEnd = () => setIsDragging(false);

  // Wheel zoom
  const handleWheel = (e: React.WheelEvent) => {
    e.preventDefault();
    setFov((prev) => Math.max(40, Math.min(105, prev + (e.deltaY > 0 ? 4 : -4))));
  };

  // Convert spherical (yaw, pitch) to screen (x, y) percent
  const projectHotspotToScreen = (hotspotYaw: number, hotspotPitch: number) => {
    let deltaYaw = hotspotYaw - yaw;
    while (deltaYaw > 180) deltaYaw -= 360;
    while (deltaYaw < -180) deltaYaw += 360;

    const deltaPitch = hotspotPitch - pitch;

    const halfFovX = fov / 2;
    const halfFovY = (fov * 0.6) / 2;

    if (Math.abs(deltaYaw) > halfFovX || Math.abs(deltaPitch) > halfFovY) {
      return null; // Outside viewport
    }

    const x = 50 + (deltaYaw / halfFovX) * 50;
    const y = 50 - (deltaPitch / halfFovY) * 50;

    return { x, y };
  };

  return (
    <div
      ref={containerRef}
      onWheel={handleWheel}
      className="relative w-full h-[450px] sm:h-[550px] rounded-3xl overflow-hidden bg-slate-950 border border-slate-800 shadow-2xl select-none group"
    >
      {/* Canvas */}
      <canvas
        ref={canvasRef}
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseUp}
        onTouchStart={handleTouchStart}
        onTouchMove={handleTouchMove}
        onTouchEnd={handleTouchEnd}
        className={`w-full h-full block cursor-grab ${isDragging ? 'cursor-grabbing' : ''}`}
      />

      {/* Interactive Projected Hotspot Pins */}
      {scene.hotspots.map((h) => {
        const pos = projectHotspotToScreen(h.yaw, h.pitch);
        if (!pos) return null;

        const isSelected = activeHotspot?.hotspot_id === h.hotspot_id;

        return (
          <div
            key={h.hotspot_id}
            style={{ left: `${pos.x}%`, top: `${pos.y}%` }}
            onClick={(e) => {
              e.stopPropagation();
              setActiveHotspot(h);
            }}
            className="absolute -translate-x-1/2 -translate-y-1/2 z-20 cursor-pointer transition-transform hover:scale-125"
          >
            <div
              className={`p-2 rounded-full shadow-lg border-2 flex items-center justify-center transition-all ${
                isSelected
                  ? 'bg-amber-400 text-slate-950 border-white scale-125 shadow-amber-400/50'
                  : 'bg-blue-600 text-white border-white/90 hover:bg-blue-500 shadow-blue-500/40'
              }`}
            >
              <MapPin className="w-4 h-4" />
            </div>

            {/* Hotspot floating badge label */}
            <div className="absolute top-8 left-1/2 -translate-x-1/2 whitespace-nowrap px-2.5 py-1 rounded-lg bg-slate-900/90 text-white text-[10px] font-bold tracking-wide border border-slate-700 pointer-events-none shadow-md backdrop-blur-xs">
              {h.title}
            </div>
          </div>
        );
      })}

      {/* Active Hotspot Overlay Modal */}
      {activeHotspot && (
        <XRHotspotOverlay
          hotspot={activeHotspot}
          onClose={() => setActiveHotspot(null)}
          onTriggerAction={(h) => {
            if (h.target_id && onSelectWayfinding) {
              onSelectWayfinding(h.target_id);
            }
          }}
        />
      )}

      {/* Floating HUD Controls */}
      <div className="absolute top-4 left-4 z-20 flex items-center gap-2">
        <div className="flex items-center gap-2 px-3 py-1.5 rounded-xl bg-slate-900/80 text-white backdrop-blur-md border border-slate-700/80 text-xs font-mono font-medium shadow-md">
          <Compass className="w-3.5 h-3.5 text-blue-400" />
          <span>Yaw: {Math.round(yaw)}°</span>
          <span className="text-slate-600">·</span>
          <span>Pitch: {Math.round(pitch)}°</span>
        </div>

        {/* AR Simulator Toggle Button */}
        <button
          type="button"
          onClick={() => setIsARSimulated((prev) => !prev)}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold backdrop-blur-md border transition-all ${
            isARSimulated
              ? 'bg-emerald-600 text-white border-emerald-400 shadow-md shadow-emerald-500/20'
              : 'bg-slate-900/80 text-slate-300 border-slate-700/80 hover:bg-slate-800'
          }`}
          title="Toggle AR Spatial Viewport Overlay"
        >
          <Camera className="w-3.5 h-3.5" />
          <span>{isARSimulated ? 'AR Mode Active' : 'Enter AR Mode'}</span>
        </button>
      </div>

      {/* Action Control Buttons (Top Right) */}
      <div className="absolute top-4 right-4 z-20 flex items-center gap-1.5">
        <button
          type="button"
          onClick={() => setFov((prev) => Math.max(40, prev - 10))}
          className="p-2 rounded-xl bg-slate-900/80 text-slate-300 hover:text-white hover:bg-slate-800 backdrop-blur-md border border-slate-700/80 transition-colors shadow-md"
          title="Zoom In"
        >
          <ZoomIn className="w-4 h-4" />
        </button>
        <button
          type="button"
          onClick={() => setFov((prev) => Math.min(100, prev + 10))}
          className="p-2 rounded-xl bg-slate-900/80 text-slate-300 hover:text-white hover:bg-slate-800 backdrop-blur-md border border-slate-700/80 transition-colors shadow-md"
          title="Zoom Out"
        >
          <ZoomOut className="w-4 h-4" />
        </button>
        <button
          type="button"
          onClick={() => {
            setYaw(180);
            setPitch(0);
            setFov(75);
            setActiveHotspot(null);
          }}
          className="p-2 rounded-xl bg-slate-900/80 text-slate-300 hover:text-white hover:bg-slate-800 backdrop-blur-md border border-slate-700/80 transition-colors shadow-md"
          title="Reset Camera Orientation"
        >
          <RotateCcw className="w-4 h-4" />
        </button>
        <button
          type="button"
          onClick={toggleFullscreen}
          className="p-2 rounded-xl bg-slate-900/80 text-slate-300 hover:text-white hover:bg-slate-800 backdrop-blur-md border border-slate-700/80 transition-colors shadow-md"
          title="Toggle Fullscreen"
        >
          {isFullscreen ? <Minimize2 className="w-4 h-4" /> : <Maximize2 className="w-4 h-4" />}
        </button>
      </div>

      {/* Bottom Drag Guidance Banner */}
      <div className="absolute bottom-4 right-4 z-10 pointer-events-none hidden sm:flex items-center gap-1.5 px-3 py-1 rounded-full bg-slate-900/60 text-slate-400 text-[11px] font-mono backdrop-blur-xs border border-slate-800">
        <Sparkles className="w-3 h-3 text-blue-400" />
        <span>Drag to rotate 360° · Click pin for wayfinding</span>
      </div>
    </div>
  );
};
