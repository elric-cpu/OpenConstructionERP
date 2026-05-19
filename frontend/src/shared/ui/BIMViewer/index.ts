export { BIMViewer, DisciplineToggle } from './BIMViewer';
export type { BIMViewerProps, BIMViewMode } from './BIMViewer';

export { SceneManager } from './SceneManager';
export type { Viewpoint as SceneViewpoint } from './SceneManager';

export { ElementManager } from './ElementManager';
export type { BIMElementData, BIMModelData, BIMBoundingBox } from './ElementManager';

export { SelectionManager } from './SelectionManager';
export type { SelectionCallbacks } from './SelectionManager';

export { MeasureManager } from './MeasureManager';
export type { Measurement, MeasureState, MeasureKind } from './MeasureManager';

export { ClipManager } from './ClipManager';
export type {
  ClipMode,
  ClipAxis,
  ClipBoxExtent,
  ClipPlaneState,
} from './ClipManager';

export {
  deriveGeometry,
  deriveRelations,
} from './canonicalElementDetails';
export type {
  CanonicalGeometry,
  CanonicalRelation,
  CanonicalBBox,
} from './canonicalElementDetails';

export {
  distance3,
  polygonArea3,
  polygonPerimeter3,
  angleBetween3,
  centroid3,
} from './measureMath';
export type { Vec3 } from './measureMath';

export {
  addViewpoint,
  listViewpoints,
  removeViewpoint,
  renameViewpoint,
  getViewpoint,
} from './SavedViewsStore';
export type { Viewpoint } from './SavedViewsStore';
