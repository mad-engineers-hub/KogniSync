/**
 * frontend/src/utils/mapViewportManager.ts
 *
 * Viewport Persistence & Intentional Fit Manager for Leaflet Journey Maps.
 *
 * Implements strict viewport persistence invariants:
 * 1. Automatic fitBounds occurs strictly ONCE upon loading a genuinely new journey identity.
 * 2. User-controlled zoom and pan persist across re-renders, route geometry enrichment,
 *    marker updates, active segment clicks, and background data polling.
 * 3. ResizeObserver calls invalidateSize({ pan: false }) without resetting zoom or pan.
 * 4. Switching to a different journey identity triggers one intentional viewport adjustment
 *    governed by the chosen ViewportSwitchPolicy:
 *    - 'fresh_framing' (Default): Each journey selection frames the complete corridor of that journey.
 *    - 'restore_saved': Returning to a previously viewed journey restores its saved zoom/center.
 * 5. Explicit user actions ("Fit Whole Route", "Focus Origin", "Focus Destination")
 *    intentionally adjust the viewport and reset user-adjusted state appropriately.
 * 6. Programmatic animation lifecycle is guarded: genuine manual pointer drag immediately overrides
 *    in-flight programmatic movement, and moveend events release the lock promptly.
 */

import type L from 'leaflet';
import { isValidCoordinate } from './mapCoordinates';

export interface ViewportFitPadding {
  paddingTopLeft: [number, number];
  paddingBottomRight: [number, number];
  maxZoom?: number;
}

export type ViewportSwitchPolicy = 'fresh_framing' | 'restore_saved';

export interface MapViewportManagerOptions {
  customPadding?: Partial<ViewportFitPadding>;
  switchPolicy?: ViewportSwitchPolicy;
}

export interface ViewportSnapshot {
  journeyId: string | null;
  lastFittedJourneyId: string | null;
  hasUserAdjustedViewport: boolean;
  isProgrammaticFitting: boolean;
  fitBoundsCallCount: number;
  autoFitCallCount: number;
  explicitFitCallCount: number;
  switchPolicy: ViewportSwitchPolicy;
  savedViewportsCount: number;
}

export interface SavedViewport {
  center: [number, number];
  zoom: number;
}

export type BoundingBoxExpression = [[number, number], [number, number]] | L.LatLngBounds;

export interface MapViewportTarget {
  fitBounds(bounds: any, options?: any): void;
  invalidateSize(options?: { pan?: boolean; debounceMoveend?: boolean }): void;
  stop(): void;
  zoomIn?(delta?: number): void;
  zoomOut?(delta?: number): void;
  setView?(center: [number, number], zoom?: number, options?: any): void;
  getZoom?(): number;
  getCenter?(): [number, number] | { lat: number; lng: number };
  on(event: string, fn: (...args: any[]) => void): void;
  off(event: string, fn: (...args: any[]) => void): void;
  once?(event: string, fn: (...args: any[]) => void): void;
}

export class MapViewportManager {
  private lastFittedJourneyId: string | null = null;
  private hasUserAdjustedViewport: boolean = false;
  private isProgrammaticFitting: boolean = false;
  private fitBoundsCallCount: number = 0;
  private autoFitCallCount: number = 0;
  private explicitFitCallCount: number = 0;
  private activeMap: MapViewportTarget | null = null;
  private userInteractionListeners: { event: string; fn: () => void }[] = [];
  private programmaticFitTimer: any = null;
  private switchPolicy: ViewportSwitchPolicy = 'fresh_framing';
  private savedViewports: Map<string, SavedViewport> = new Map();

  private defaultPadding: ViewportFitPadding = {
    paddingTopLeft: [45, 45],
    paddingBottomRight: [45, 75],
    maxZoom: 14,
  };

  constructor(options?: MapViewportManagerOptions | Partial<ViewportFitPadding>) {
    if (options) {
      if ('switchPolicy' in options && options.switchPolicy) {
        this.switchPolicy = options.switchPolicy;
      }
      if ('customPadding' in options && options.customPadding) {
        this.defaultPadding = { ...this.defaultPadding, ...options.customPadding };
      } else if (!('switchPolicy' in options)) {
        this.defaultPadding = { ...this.defaultPadding, ...(options as Partial<ViewportFitPadding>) };
      }
    }
  }

  /**
   * Configure the journey switching policy.
   */
  public setSwitchPolicy(policy: ViewportSwitchPolicy): void {
    this.switchPolicy = policy;
  }

  public getSwitchPolicy(): ViewportSwitchPolicy {
    return this.switchPolicy;
  }

  /**
   * Attach map event listeners to detect manual user zoom and pan.
   * Listeners are idempotent and attached only once per map instance.
   */
  public attachMap(map: MapViewportTarget): void {
    if (this.activeMap === map) return;
    this.detachMap();
    this.activeMap = map;

    const syncTelemetry = () => {
      if (typeof window !== 'undefined') {
        (window as any).__KOGNISYNC_VIEWPORT_TELEMETRY__ = this.getSnapshot();
      }
    };

    // dragstart is exclusively triggered by user pointer/touch interactions
    const onDragStart = () => {
      if (this.isProgrammaticFitting) {
        this.clearProgrammaticFitting();
        if (typeof map.stop === 'function') {
          map.stop();
        }
      }
      this.hasUserAdjustedViewport = true;
      syncTelemetry();
    };

    // zoomstart and movestart can be programmatic or user-initiated
    const onZoomOrMoveStart = () => {
      if (!this.isProgrammaticFitting) {
        this.hasUserAdjustedViewport = true;
        syncTelemetry();
      }
    };

    // moveend / zoomend releases programmatic lock when animation settles
    const onMoveOrZoomEnd = () => {
      if (this.isProgrammaticFitting) {
        this.clearProgrammaticFitting();
      }
    };

    const listeners = [
      { event: 'dragstart', fn: onDragStart },
      { event: 'zoomstart', fn: onZoomOrMoveStart },
      { event: 'movestart', fn: onZoomOrMoveStart },
      { event: 'moveend', fn: onMoveOrZoomEnd },
      { event: 'zoomend', fn: onMoveOrZoomEnd },
    ];

    listeners.forEach(({ event, fn }) => {
      map.on(event, fn);
      this.userInteractionListeners.push({ event, fn });
    });
  }

  /**
   * Detach all map listeners when map unmounts.
   */
  public detachMap(): void {
    if (this.activeMap) {
      this.userInteractionListeners.forEach(({ event, fn }) => {
        this.activeMap?.off(event, fn);
      });
      this.userInteractionListeners = [];
      this.activeMap = null;
    }
  }

  /**
   * Check whether a new journey identity requires automatic viewport fitting.
   */
  public shouldFitJourney(journeyId: string): boolean {
    return this.lastFittedJourneyId !== journeyId;
  }

  /**
   * Clear programmatic fitting flag and safety timer immediately.
   */
  public clearProgrammaticFitting(): void {
    if (this.programmaticFitTimer) {
      clearTimeout(this.programmaticFitTimer);
      this.programmaticFitTimer = null;
    }
    this.isProgrammaticFitting = false;
  }

  /**
   * Capture current map center and zoom level if map supports inspection.
   */
  private captureCurrentMapViewport(map: MapViewportTarget): SavedViewport | null {
    if (typeof map.getZoom !== 'function' || typeof map.getCenter !== 'function') {
      return null;
    }
    const zoom = map.getZoom();
    const rawCenter = map.getCenter();
    let center: [number, number];
    if (Array.isArray(rawCenter)) {
      center = [rawCenter[0], rawCenter[1]];
    } else if (rawCenter && typeof rawCenter === 'object' && 'lat' in rawCenter && 'lng' in rawCenter) {
      center = [rawCenter.lat, rawCenter.lng];
    } else {
      return null;
    }
    return { center, zoom };
  }

  /**
   * Handle journey render pass: fits bounds strictly once when a new journey identity appears.
   * Skips fitBounds on ordinary re-renders, marker updates, or if user has zoomed/panned.
   *
   * @returns true if viewport was adjusted (fitBounds or setView), false if skipped.
   */
  public onJourneyRender(
    journeyId: string,
    points: [number, number][],
    map: MapViewportTarget,
    animate: boolean = false
  ): boolean {
    if (!this.shouldFitJourney(journeyId)) {
      // Journey identity unchanged. Preserve user viewport across re-renders.
      return false;
    }

    // If switching away from a previously active journey, save its custom viewport if requested
    if (this.lastFittedJourneyId && this.lastFittedJourneyId !== journeyId) {
      if (this.hasUserAdjustedViewport) {
        const currentVp = this.captureCurrentMapViewport(map);
        if (currentVp) {
          this.savedViewports.set(this.lastFittedJourneyId, currentVp);
        }
      }
    }

    // Policy: 'restore_saved' restores user's previous zoom/center if one was saved
    if (this.switchPolicy === 'restore_saved' && this.savedViewports.has(journeyId)) {
      const saved = this.savedViewports.get(journeyId)!;
      map.stop();
      this.clearProgrammaticFitting();

      if (typeof map.setView === 'function') {
        this.isProgrammaticFitting = true;
        map.setView(saved.center, saved.zoom, { animate });
        this.lastFittedJourneyId = journeyId;
        this.hasUserAdjustedViewport = true;

        if (!animate) {
          this.clearProgrammaticFitting();
        } else {
          this.programmaticFitTimer = setTimeout(() => {
            this.clearProgrammaticFitting();
          }, 350);
        }
        return true;
      }
    }

    // Policy: 'fresh_framing' (Default) or first-time view: compute bounds and frame corridor
    const validPoints = points.filter(([lat, lng]) => isValidCoordinate(lat, lng));
    if (validPoints.length === 0) {
      // Do not mark as fitted until valid geographic coordinates are available
      return false;
    }

    let minLat = Infinity;
    let maxLat = -Infinity;
    let minLng = Infinity;
    let maxLng = -Infinity;

    for (const [lat, lng] of validPoints) {
      if (lat < minLat) minLat = lat;
      if (lat > maxLat) maxLat = lat;
      if (lng < minLng) minLng = lng;
      if (lng > maxLng) maxLng = lng;
    }

    if (!isFinite(minLat) || !isFinite(maxLat) || !isFinite(minLng) || !isFinite(maxLng)) {
      return false;
    }

    const boundsObj: [[number, number], [number, number]] = [
      [minLat, minLng],
      [maxLat, maxLng],
    ];

    // Cancel any in-flight animations before programmatic fit
    map.stop();
    this.clearProgrammaticFitting();

    try {
      this.isProgrammaticFitting = true;
      this.autoFitCallCount++;
      this.fitBoundsCallCount++;

      map.fitBounds(boundsObj, {
        paddingTopLeft: this.defaultPadding.paddingTopLeft,
        paddingBottomRight: this.defaultPadding.paddingBottomRight,
        maxZoom: this.defaultPadding.maxZoom,
        animate,
      });
    } finally {
      if (!animate) {
        // Immediate completion when animation is disabled
        this.clearProgrammaticFitting();
      } else {
        // Fallback safety timer if Leaflet moveend does not fire (e.g. view already at target bounds)
        this.programmaticFitTimer = setTimeout(() => {
          this.clearProgrammaticFitting();
        }, 400);
      }
    }

    this.lastFittedJourneyId = journeyId;
    this.hasUserAdjustedViewport = false;
    return true;
  }

  /**
   * Explicit user action: "Fit Whole Route".
   * Recovers full route framing, clears saved custom viewport for this journey, and resets user-adjusted flag.
   */
  public onExplicitFitRoute(map: MapViewportTarget, bounds: any): boolean {
    if (!bounds) return false;
    if (typeof bounds.isValid === 'function' && !bounds.isValid()) return false;

    if (this.lastFittedJourneyId) {
      this.savedViewports.delete(this.lastFittedJourneyId);
    }

    map.stop();
    map.invalidateSize({ pan: false });
    this.clearProgrammaticFitting();

    try {
      this.isProgrammaticFitting = true;
      this.hasUserAdjustedViewport = false;
      this.explicitFitCallCount++;
      this.fitBoundsCallCount++;

      map.fitBounds(bounds, {
        paddingTopLeft: this.defaultPadding.paddingTopLeft,
        paddingBottomRight: this.defaultPadding.paddingBottomRight,
        maxZoom: this.defaultPadding.maxZoom,
        animate: true,
      });
    } finally {
      this.programmaticFitTimer = setTimeout(() => {
        this.clearProgrammaticFitting();
      }, 400);
    }

    return true;
  }

  /**
   * User interaction: zoom control clicked.
   */
  public onUserZoom(map: MapViewportTarget, direction: 'in' | 'out'): void {
    this.hasUserAdjustedViewport = true;
    if (typeof window !== 'undefined') {
      (window as any).__KOGNISYNC_VIEWPORT_TELEMETRY__ = this.getSnapshot();
    }
    if (direction === 'in') {
      if (typeof map.zoomIn === 'function') map.zoomIn();
    } else {
      if (typeof map.zoomOut === 'function') map.zoomOut();
    }
  }

  /**
   * User interaction: recenter on origin or destination.
   */
  public onUserRecenter(map: MapViewportTarget, lat: number, lng: number, zoom: number = 13): void {
    this.hasUserAdjustedViewport = true;
    if (typeof window !== 'undefined') {
      (window as any).__KOGNISYNC_VIEWPORT_TELEMETRY__ = this.getSnapshot();
    }
    if (typeof map.setView === 'function') {
      map.setView([lat, lng], zoom, { animate: true });
    }
  }

  /**
   * Responsive container resize: invalidateSize without altering viewport center or zoom.
   */
  public onResize(map: MapViewportTarget): void {
    map.invalidateSize({ pan: false });
  }

  /**
   * Telemetry snapshot for testing and verification.
   */
  public getSnapshot(currentJourneyId?: string): ViewportSnapshot {
    return {
      journeyId: currentJourneyId ?? this.lastFittedJourneyId,
      lastFittedJourneyId: this.lastFittedJourneyId,
      hasUserAdjustedViewport: this.hasUserAdjustedViewport,
      isProgrammaticFitting: this.isProgrammaticFitting,
      fitBoundsCallCount: this.fitBoundsCallCount,
      autoFitCallCount: this.autoFitCallCount,
      explicitFitCallCount: this.explicitFitCallCount,
      switchPolicy: this.switchPolicy,
      savedViewportsCount: this.savedViewports.size,
    };
  }

  /**
   * Retrieve saved viewport for a journey ID (if any).
   */
  public getSavedViewport(journeyId: string): SavedViewport | undefined {
    return this.savedViewports.get(journeyId);
  }

  /**
   * Manual interaction flag setter (for tests or synthetic events).
   */
  public setUserAdjusted(adjusted: boolean): void {
    this.hasUserAdjustedViewport = adjusted;
  }

  /**
   * Reset state (on component unmount).
   */
  public reset(): void {
    this.detachMap();
    this.clearProgrammaticFitting();
    this.lastFittedJourneyId = null;
    this.hasUserAdjustedViewport = false;
    this.isProgrammaticFitting = false;
    this.fitBoundsCallCount = 0;
    this.autoFitCallCount = 0;
    this.explicitFitCallCount = 0;
    this.savedViewports.clear();
  }
}
