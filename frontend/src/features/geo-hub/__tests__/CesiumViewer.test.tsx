// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
/**
 * CesiumViewer tests. Mocks the dynamic ``import('cesium')`` so the
 * viewer initialises against a stub, then asserts:
 *
 * 1. The container is rendered.
 * 2. The Cesium loading/absent message is shown when ``cesium`` cannot
 *    be imported (community-build behaviour).
 * 3. The component cleans up on unmount (destroy() called).
 * 4. A tileset URL from ``mapConfig.tilesets`` triggers
 *    ``Cesium3DTileset.fromUrl(url)`` exactly once per tileset.
 * 5. The viewer flies to the anchor when present.
 */

import { render, screen, waitFor, cleanup } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { CesiumViewer } from '../CesiumViewer';
import type { MapConfig } from '../types';

// Build a fresh stub per test so destroy() / fromUrl() spies are isolated.
function makeCesiumStub() {
  const flyTo = vi.fn();
  const destroy = vi.fn();
  const add = vi.fn();
  // ``fromUrl`` now receives a Cesium ``Resource`` (so child-tile requests
  // carry our bearer token), not the raw uri string. Accept either shape.
  const fromUrl = vi.fn(async (urlOrResource: { url?: string } | string) => ({
    url: typeof urlOrResource === 'string' ? urlOrResource : urlOrResource?.url,
    boundingSphere: null,
  }));
  // Constructor for a Cesium ``Resource`` — records the url + headers the
  // viewer attaches so the tileset test can assert on the resolved route.
  const Resource = vi.fn().mockImplementation(
    (opts: { url?: string; headers?: Record<string, string> }) => ({
      url: opts?.url,
      headers: opts?.headers,
      _isResource: true,
    }),
  );
  // Minimal canvas + camera-event stubs so the live-HUD wiring exercises
  // its setInputAction / camera.changed branches without throwing.
  // Listeners are kept in arrays so individual tests can introspect or
  // fire synthetic events when they want to assert HUD plumbing.
  const inputActions = new Map<number, (m: { endPosition: { x: number; y: number } }) => void>();
  const cameraListeners: Array<() => void> = [];
  const canvas = document.createElement('canvas');
  const ssehDestroy = vi.fn();
  const ScreenSpaceEventHandler = vi.fn().mockImplementation(() => ({
    setInputAction: vi.fn((cb, type) => inputActions.set(type, cb)),
    removeInputAction: vi.fn((type) => inputActions.delete(type)),
    destroy: ssehDestroy,
  }));
  return {
    flyTo,
    destroy,
    add,
    fromUrl,
    Resource,
    canvas,
    inputActions,
    cameraListeners,
    ScreenSpaceEventHandler,
    ssehDestroy,
    module: {
      Viewer: vi.fn().mockImplementation(() => ({
        destroy,
        camera: {
          flyTo,
          heading: 0,
          positionCartographic: { longitude: 0, latitude: 0, height: 1000 },
          changed: {
            addEventListener: (cb: () => void) => {
              cameraListeners.push(cb);
              return () => {
                const idx = cameraListeners.indexOf(cb);
                if (idx >= 0) cameraListeners.splice(idx, 1);
              };
            },
            removeEventListener: (cb: () => void) => {
              const idx = cameraListeners.indexOf(cb);
              if (idx >= 0) cameraListeners.splice(idx, 1);
            },
          },
        },
        scene: {
          primitives: { add },
          canvas,
          pickPosition: vi.fn(() => ({ x: 1, y: 2, z: 3 })),
        },
        entities: {
          add: vi.fn((e) => e),
          remove: vi.fn(() => true),
          removeAll: vi.fn(),
          values: [],
        },
        shadows: false,
      })),
      Cartesian3: {
        fromDegrees: vi.fn((lon, lat, alt) => ({ lon, lat, alt })),
      },
      Cartographic: {
        fromCartesian: vi.fn(() => ({
          longitude: 0.1,
          latitude: 0.2,
          height: 42,
        })),
      },
      Color: {
        RED: 'red',
        ORANGE: 'orange',
        DODGERBLUE: 'dodgerblue',
        WHITE: 'white',
        fromCssColorString: vi.fn((css: string) => css),
      },
      EllipsoidTerrainProvider: vi.fn(),
      // OSM base imagery — viewer init wires
      // ``baseLayer: new ImageryLayer(new UrlTemplateImageryProvider({...}))``
      // so both must be present on the mock or the stubbed Viewer constructor
      // never runs (vi.doMock throws on unknown property access).
      ImageryLayer: vi.fn(),
      UrlTemplateImageryProvider: vi.fn(),
      // Cesium >= 1.107 keys "default Ion token" detection off
      // ``Ion.defaultAccessToken``; we set a sentinel string at boot to
      // silence the watermark. Stub it so the assignment is a no-op.
      Ion: { defaultAccessToken: '' },
      Cesium3DTileset: { fromUrl },
      // Cesium fetches tileset.json + its child tiles itself, so the viewer
      // wraps the artifact route in a Resource that carries the bearer token.
      Resource,
      // Per-tile colour/opacity styling — feature-detected by the viewer.
      Cesium3DTileStyle: vi
        .fn()
        .mockImplementation((opts: Record<string, unknown>) => ({ ...opts })),
      // Sphere math for the "Fit to data" auto-zoom.
      BoundingSphere: {
        fromPoints: vi.fn(() => ({ center: { x: 0, y: 0, z: 0 }, radius: 100 })),
        fromBoundingSpheres: vi.fn(() => ({
          center: { x: 0, y: 0, z: 0 },
          radius: 100,
        })),
      },
      ScreenSpaceEventHandler,
      ScreenSpaceEventType: { MOUSE_MOVE: 15, LEFT_CLICK: 2 },
      // SceneMode enum — read at viewer init to honour the saved projection
      // preference; a missing export here throws before ``new Viewer``.
      SceneMode: { MORPHING: 0, COLUMBUS_VIEW: 1, SCENE2D: 2, SCENE3D: 3 },
      Math: {
        toDegrees: (r: number) => (r * 180) / Math.PI,
        TWO_PI: Math.PI * 2,
      },
    },
  };
}

afterEach(() => {
  vi.resetModules();
  cleanup();
});

describe('CesiumViewer', () => {
  it('renders a Cesium container element', async () => {
    vi.doMock('cesium', () => ({}));
    render(<CesiumViewer mode="global" />);
    const container = await screen.findByTestId('geo-hub-cesium-container');
    expect(container).toBeTruthy();
  });

  it('shows install hint when cesium import fails', async () => {
    // Force the absent branch deterministically: an empty module has no
    // ``Viewer`` export, so ``loadCesium`` returns null and the install
    // hint renders. Relying on cesium being physically absent is flaky —
    // it is a real dependency that CI installs, in which case the import
    // resolves and ``new Viewer()`` throws under jsdom (init_failed) rather
    // than going absent.
    vi.doMock('cesium', () => ({}));
    render(<CesiumViewer mode="global" />);
    // After the visual elevation pass the absent state shows both a
    // heading and a paragraph mentioning Cesium, so target the
    // ``npm install cesium`` <code> element which is unique.
    await waitFor(() => {
      expect(screen.getByText('npm install cesium')).toBeInTheDocument();
    });
  });

  it('flies to the anchor when mapConfig has one', async () => {
    const stub = makeCesiumStub();
    vi.doMock('cesium', () => stub.module);
    const cfg: MapConfig = {
      project_id: 'p1',
      anchor: {
        id: 'a1',
        project_id: 'p1',
        lat: '52.52',
        lon: '13.40',
        alt: '10',
        epsg_code: 4326,
        region_code: 'DE-BE',
        address: null,
        accuracy_m: null,
        metadata: {},
        created_at: '',
        updated_at: '',
      },
      imagery_layers: [],
      terrain_source: null,
      tilesets: [],
      overlays: [],
      viewpoints: [],
      active_jobs: [],
    };
    render(<CesiumViewer mode="project" mapConfig={cfg} />);
    await waitFor(() => {
      expect(stub.flyTo).toHaveBeenCalled();
    });
  });

  it('attempts to load every ready tileset', async () => {
    const stub = makeCesiumStub();
    vi.doMock('cesium', () => stub.module);
    const cfg: MapConfig = {
      project_id: 'p1',
      anchor: null,
      imagery_layers: [],
      terrain_source: null,
      tilesets: [
        {
          id: 't1',
          project_id: 'p1',
          source_kind: 'bim_model',
          source_id: 's1',
          name: 'T1',
          bucket: '',
          prefix: '',
          tileset_json_uri: 'https://x/t1/tileset.json',
          bounding_volume: null,
          geometric_error: '50',
          tile_format: 'b3dm',
          tile_count: 1,
          total_bytes: 1000,
          status: 'ready',
          generated_at: null,
          generation_job_id: null,
          metadata: {},
          created_at: '',
          updated_at: '',
        },
        {
          id: 't2',
          project_id: 'p1',
          source_kind: 'bim_model',
          source_id: 's2',
          name: 'T2',
          bucket: '',
          prefix: '',
          tileset_json_uri: null,
          bounding_volume: null,
          geometric_error: '0',
          tile_format: 'b3dm',
          tile_count: 0,
          total_bytes: 0,
          status: 'draft',
          generated_at: null,
          generation_job_id: null,
          metadata: {},
          created_at: '',
          updated_at: '',
        },
      ],
      overlays: [],
      viewpoints: [],
      active_jobs: [],
    };
    render(<CesiumViewer mode="project" mapConfig={cfg} />);
    await waitFor(() => {
      expect(stub.fromUrl).toHaveBeenCalledTimes(1);
    });
    // ``fromUrl`` now receives a Cesium ``Resource`` (so the bearer token
    // rides along to the child-tile requests), not the raw storage uri. The
    // url is our tenant-scoped artifact route keyed by the tileset id. The
    // draft tileset (no uri) must not be requested.
    expect(stub.Resource).toHaveBeenCalledTimes(1);
    const resourceArg = stub.Resource.mock.calls[0][0];
    expect(resourceArg.url).toContain('/tilesets/t1/artifact/tileset.json');
  });

  it('destroys the viewer on unmount', async () => {
    const stub = makeCesiumStub();
    vi.doMock('cesium', () => stub.module);
    const { unmount } = render(<CesiumViewer mode="global" />);
    await waitFor(() => {
      expect(stub.module.Viewer).toHaveBeenCalled();
    });
    unmount();
    expect(stub.destroy).toHaveBeenCalled();
  });

  it('emits camera state synchronously after the viewer comes up', async () => {
    // The HUD reads camera altitude + heading via ``onCameraChange``.
    // We seed the viewer with a non-trivial position (heading π/2 →
    // 90°, height 750 m) and assert the callback fires with those
    // values once init completes — without the caller having to nudge
    // the camera.
    const stub = makeCesiumStub();
    // Patch the viewer factory to seed heading + altitude on the camera.
    stub.module.Viewer = vi.fn().mockImplementation(() => ({
      destroy: stub.destroy,
      camera: {
        flyTo: stub.flyTo,
        heading: Math.PI / 2,
        positionCartographic: { longitude: 0, latitude: 0, height: 750 },
        changed: {
          addEventListener: (cb: () => void) => {
            stub.cameraListeners.push(cb);
            return () => {
              const idx = stub.cameraListeners.indexOf(cb);
              if (idx >= 0) stub.cameraListeners.splice(idx, 1);
            };
          },
          removeEventListener: vi.fn(),
        },
      },
      scene: {
        primitives: { add: stub.add },
        canvas: stub.canvas,
        pickPosition: vi.fn(() => ({ x: 1, y: 2, z: 3 })),
      },
      entities: {
        add: vi.fn((e) => e),
        remove: vi.fn(() => true),
        removeAll: vi.fn(),
        values: [],
      },
      shadows: false,
    }));
    vi.doMock('cesium', () => stub.module);
    const onCameraChange = vi.fn();
    render(
      <CesiumViewer mode="global" onCameraChange={onCameraChange} />,
    );
    await waitFor(() => {
      expect(onCameraChange).toHaveBeenCalled();
    });
    const last = onCameraChange.mock.calls.at(-1)?.[0];
    expect(last.headingDeg).toBeCloseTo(90, 5);
    expect(last.cameraAltitudeM).toBe(750);
  });

  it('forwards mouse-move picks as cursor coordinates', async () => {
    // Simulates the user moving the pointer over the globe. The stub
    // captures the registered MOUSE_MOVE input action; we invoke it
    // directly with a synthetic endPosition then assert the throttled
    // rAF flush delivers a {lat, lon, altitudeM} to the parent.
    const stub = makeCesiumStub();
    vi.doMock('cesium', () => stub.module);
    const onMouseMove = vi.fn();
    render(
      <CesiumViewer mode="global" onMouseMove={onMouseMove} />,
    );
    // Wait for the input action to be registered (eventType 15 = MOUSE_MOVE).
    await waitFor(() => {
      expect(stub.inputActions.has(15)).toBe(true);
    });
    const handler = stub.inputActions.get(15)!;
    handler({ endPosition: { x: 100, y: 200 } });
    // The flush is scheduled via rAF; rAF in JSDOM resolves on
    // microtask tick.
    await waitFor(() => {
      expect(onMouseMove).toHaveBeenCalled();
    });
    const coords = onMouseMove.mock.calls.at(-1)?.[0];
    expect(coords).not.toBeNull();
    expect(coords.lat).toBeCloseTo((0.2 * 180) / Math.PI, 5);
    expect(coords.lon).toBeCloseTo((0.1 * 180) / Math.PI, 5);
    expect(coords.altitudeM).toBe(42);
  });

  it('tears down the input handler and camera listener on unmount', async () => {
    // Live-HUD listeners must not outlive the viewer. We grab the
    // input-handler destroy spy + the camera-listener array, then
    // assert both are zeroed after unmount.
    const stub = makeCesiumStub();
    vi.doMock('cesium', () => stub.module);
    const { unmount } = render(
      <CesiumViewer
        mode="global"
        onMouseMove={vi.fn()}
        onCameraChange={vi.fn()}
      />,
    );
    await waitFor(() => {
      expect(stub.module.Viewer).toHaveBeenCalled();
    });
    // Listener should be registered once during init (the immediate
    // emit doesn't add another).
    expect(stub.cameraListeners.length).toBeGreaterThan(0);
    unmount();
    expect(stub.ssehDestroy).toHaveBeenCalled();
    expect(stub.cameraListeners.length).toBe(0);
  });

  it('does not rebuild the viewer when only the mapConfig object reference changes', async () => {
    // Regression: React Query produces a new ``mapConfig`` reference on
    // every poll. The viewer effect must key off a stable signature
    // (anchor + ready-tileset uris) so a refetch with identical content
    // does NOT destroy and re-create the entire Cesium viewer — that
    // would wipe the user's camera state and re-download the 3 MB
    // runtime every 30 s.
    const stub = makeCesiumStub();
    vi.doMock('cesium', () => stub.module);
    const makeCfg = (): MapConfig => ({
      project_id: 'p1',
      anchor: {
        id: 'a1',
        project_id: 'p1',
        lat: '52.52',
        lon: '13.40',
        alt: '10',
        epsg_code: 4326,
        region_code: 'DE-BE',
        address: null,
        accuracy_m: null,
        metadata: {},
        created_at: '',
        updated_at: '',
      },
      imagery_layers: [],
      terrain_source: null,
      tilesets: [],
      overlays: [],
      viewpoints: [],
      active_jobs: [],
    });

    const { rerender } = render(
      <CesiumViewer mode="project" mapConfig={makeCfg()} />,
    );
    await waitFor(() => {
      expect(stub.module.Viewer).toHaveBeenCalledTimes(1);
    });
    // Identical content, fresh reference — must NOT rebuild.
    rerender(<CesiumViewer mode="project" mapConfig={makeCfg()} />);
    // Give any pending effect a tick to run; the viewer count must stay 1.
    await new Promise((r) => setTimeout(r, 50));
    expect(stub.module.Viewer).toHaveBeenCalledTimes(1);
  });
});
