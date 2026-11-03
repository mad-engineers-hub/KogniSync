import React, { useEffect, useState } from 'react';
import { Eye, ShieldCheck, Smartphone, Monitor, Info } from 'lucide-react';
import { XRPlatform, DeviceClass } from '../../types/xr';

interface CapabilityStatus {
  webxrSupported: boolean;
  arSessionSupported: boolean;
  isMobile: boolean;
  isApple: boolean;
  activePlatform: XRPlatform;
  activeClass: DeviceClass;
}

export const XRDevicePrompt: React.FC = () => {
  const [status, setStatus] = useState<CapabilityStatus>({
    webxrSupported: false,
    arSessionSupported: false,
    isMobile: false,
    isApple: false,
    activePlatform: 'desktop_fallback',
    activeClass: 'desktop',
  });

  useEffect(() => {
    const isMobile =
      typeof navigator !== 'undefined' &&
      /android|iphone|ipad|ipod/i.test(navigator.userAgent.toLowerCase());
    const isApple =
      typeof navigator !== 'undefined' &&
      /iphone|ipad|ipod|macintosh/i.test(navigator.userAgent.toLowerCase());

    const checkWebXR = async () => {
      let webxrSupported = false;
      let arSessionSupported = false;

      if (typeof navigator !== 'undefined' && 'xr' in navigator && (navigator as any).xr?.isSessionSupported) {
        try {
          webxrSupported = await (navigator as any).xr.isSessionSupported('immersive-vr');
          arSessionSupported = await (navigator as any).xr.isSessionSupported('immersive-ar');
        } catch {
          // Unsupported or secure context restriction
        }
      }

      let activePlatform: XRPlatform = 'desktop_fallback';
      let activeClass: DeviceClass = 'desktop';

      if (webxrSupported) {
        activePlatform = 'webxr';
        activeClass = 'headset_vr';
      } else if (arSessionSupported || (isMobile && !isApple)) {
        activePlatform = 'arcore';
        activeClass = 'phone_ar';
      } else if (isApple && isMobile) {
        activePlatform = 'arkit';
        activeClass = 'phone_ar';
      }

      setStatus({
        webxrSupported,
        arSessionSupported,
        isMobile,
        isApple,
        activePlatform,
        activeClass,
      });
    };

    checkWebXR();
  }, []);

  return (
    <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-3 rounded-xl bg-slate-900/90 text-white backdrop-blur-md border border-slate-700/80 text-xs shadow-lg">
      <div className="flex items-center gap-2.5">
        <div className="p-1.5 rounded-lg bg-blue-500/20 text-blue-400">
          {status.isMobile ? <Smartphone className="w-4 h-4" /> : <Monitor className="w-4 h-4" />}
        </div>
        <div>
          <div className="flex items-center gap-1.5 font-semibold text-slate-100">
            <span>Hardware Capability:</span>
            <span className="font-mono text-blue-400 uppercase tracking-wider text-[11px] font-bold">
              {status.activePlatform.replace('_', ' ')}
            </span>
          </div>
          <div className="text-slate-400 text-[11px]">
            {status.activePlatform === 'desktop_fallback'
              ? 'High-Fidelity 360° Interactive Canvas with Hotspots & Wayfinding'
              : status.webxrSupported
              ? 'WebXR Immersive Session Ready'
              : 'Mobile Spatial AR Mode Supported'}
          </div>
        </div>
      </div>

      <div className="flex items-center gap-2">
        <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full bg-emerald-500/20 text-emerald-300 font-mono text-[11px] font-medium border border-emerald-500/30">
          <ShieldCheck className="w-3 h-3" />
          Verified Safe Mode
        </span>
      </div>
    </div>
  );
};
