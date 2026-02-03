# Instant Chart Switching Infrastructure

## Overview

This project adds infrastructure to enable instant chart type switching in Superset's Explore view without requiring a full database query round-trip. When a user switches from one chart type to another (e.g., Bar to Line), the system can reuse cached raw data and apply new post-processing operations, reducing switch time from ~500ms+ to ~50-100ms.

## Problem Statement

Currently, when a user changes the chart type (viz_type) in the Explore view:

1. The chart becomes "stale" (`chartIsStale = true`)
2. User must click "Update Chart"
3. A full API call is made to `/api/v1/chart/data`
4. The database is queried (even if the same data was just fetched)
5. Post-processing is applied server-side
6. Results are returned and rendered

This creates unnecessary latency when exploring different visualizations of the same data.

## Solution Architecture

### Key Insight

Many chart types share the same underlying query structure - they differ only in **post-processing**. For example:
- Bar chart and Line chart with the same dimensions/metrics
- Pie chart and Donut chart
- Area chart and Stacked Area chart

By caching the **raw data** (after query, before post-processing) separately, we can apply different post-processing operations without re-querying.

### Two-Cache Strategy

```
┌─────────────────────────────────────────────────────────────────┐
│                        CACHE STRUCTURE                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Processed Cache (existing)                                     │
│  ├── Key: hash(query + post_processing)                        │
│  └── Value: DataFrame after post-processing                    │
│                                                                 │
│  Raw Cache (new)                                                │
│  ├── Key: "raw-" + hash(query)  ← excludes post_processing     │
│  └── Value: DataFrame before post-processing                   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Request Flow

```
CURRENT FLOW (every viz switch):
┌──────────┐     ┌──────────┐     ┌──────────┐     ┌──────────┐
│  Client  │────▶│   API    │────▶│ Database │────▶│  Render  │
└──────────┘     └──────────┘     └──────────┘     └──────────┘
                                  ~300-500ms+

NEW FLOW (instant switch):
┌──────────┐     ┌───────────────┐     ┌──────────┐
│  Client  │────▶│ /data/transform│────▶│  Render  │
└──────────┘     └───────────────┘     └──────────┘
                 ~50-100ms (cache hit + transform)
```

## Implementation Details

### Backend Components

#### 1. QueryObject.raw_cache_key()
**File:** `superset/common/query_object.py`

Generates a cache key that excludes `post_processing`, allowing different viz types to share cached raw data.

```python
def raw_cache_key(self, **extra: Any) -> str:
    cache_dict = dict(self.to_dict())
    cache_dict.pop("post_processing", None)  # Key difference
    # ... rest of key generation
    return f"raw-{hash}"
```

#### 2. QueryResult.df_raw
**File:** `superset/models/helpers.py`

New field to capture the DataFrame before post-processing is applied.

```python
class QueryResult:
    def __init__(self, ..., df_raw: Optional[pd.DataFrame] = None):
        self.df_raw = df_raw  # Pre-post-processing DataFrame
```

#### 3. Raw Data Caching
**File:** `superset/common/query_context_processor.py`

New methods to cache raw data separately:

```python
def raw_query_cache_key(self, query_obj: QueryObject) -> str | None:
    # Generate cache key without post_processing

def _cache_raw_data(self, raw_cache_key: str, query_result: QueryResult, ...):
    # Cache the raw DataFrame
```

#### 4. Transform Endpoint
**File:** `superset/charts/data/api.py`

New endpoint to transform cached data:

```
POST /api/v1/chart/data/transform
{
    "raw_cache_key": "raw-abc123...",
    "post_processing": [
        {"operation": "pivot", "options": {...}}
    ]
}
```

#### 5. ChartDataTransformCommand
**File:** `superset/commands/chart/data/transform_command.py`

Command that:
1. Retrieves cached raw data by key
2. Applies new post-processing operations
3. Returns transformed data in standard chart response format

### Frontend Components

#### 1. Transform Actions
**File:** `superset-frontend/src/components/Chart/chartAction.js`

```javascript
export function transformCachedData(rawCacheKey, postProcessing, key) {
  return async dispatch => {
    dispatch(chartTransformStarted(key));
    const response = await SupersetClient.post({
      endpoint: '/api/v1/chart/data/transform',
      jsonPayload: { raw_cache_key: rawCacheKey, post_processing: postProcessing }
    });
    return dispatch(chartTransformSucceeded(response.json.result, key));
  };
}
```

#### 2. Reducer Handlers
**File:** `superset-frontend/src/components/Chart/chartReducer.ts`

Handles `CHART_TRANSFORM_STARTED`, `CHART_TRANSFORM_SUCCEEDED`, `CHART_TRANSFORM_FAILED` actions.

### API Response Changes

The chart data response now includes `raw_cache_key`:

```json
{
  "result": [{
    "cache_key": "abc123...",
    "raw_cache_key": "raw-def456...",  // NEW
    "data": [...],
    "colnames": [...],
    ...
  }]
}
```

## Usage

### For Developers

To use instant chart switching in a component:

```javascript
import { transformCachedData } from 'src/components/Chart/chartAction';

// When viz type changes and raw_cache_key is available
if (rawCacheKey && canInstantSwitch(oldVizType, newVizType)) {
  const postProcessing = getPostProcessingForVizType(newVizType, formData);
  dispatch(transformCachedData(rawCacheKey, postProcessing, chartKey));
} else {
  // Fall back to full query
  dispatch(exploreJSON(formData, force, timeout, chartKey));
}
```

### Compatibility Matrix

Not all viz type switches can be instant. The query structure must be compatible:

| From → To | Instant? | Notes |
|-----------|----------|-------|
| Bar → Line | ✅ | Same x/y structure |
| Bar → Pie | ✅ | Same grouping |
| Table → Bar | ✅ | Aggregation compatible |
| Line → Big Number | ❌ | Different aggregation |
| Bar → Pivot Table | ❌ | Different query structure |

## Future Work

### Phase 2: Full UI Integration

1. **VizTypeControl Integration**
   - Store `raw_cache_key` in explore state
   - Check compatibility on viz type change
   - Trigger transform instead of full query

2. **Compatibility Detection**
   - Build compatibility matrix for all viz types
   - Consider query structure (columns, metrics, filters)
   - Handle edge cases (time series, aggregations)

3. **Fallback Handling**
   - Graceful fallback when cache misses
   - Handle expired cache keys
   - Retry with full query on transform failure

### Phase 3: Optimizations

1. **Predictive Caching**
   - Pre-cache transforms for likely viz switches
   - Background transform for popular chart types

2. **Cache Warming**
   - On chart load, pre-compute common transforms
   - Store multiple post-processed versions

## Testing

### Backend Tests

```bash
# Test transform command
pytest tests/unit_tests/commands/chart/data/test_transform_command.py

# Test raw cache key generation
pytest tests/unit_tests/common/test_query_object.py -k raw_cache_key
```

### Frontend Tests

```bash
# Test transform actions
npm test -- chartAction.test.js

# Test reducer
npm test -- chartReducer.test.ts
```

### Manual Testing

1. Load a chart in Explore
2. Check response includes `raw_cache_key`
3. Use browser devtools to call transform endpoint:
   ```javascript
   fetch('/api/v1/chart/data/transform', {
     method: 'POST',
     headers: {'Content-Type': 'application/json'},
     body: JSON.stringify({
       raw_cache_key: '<from response>',
       post_processing: []
     })
   })
   ```

## Configuration

No new configuration options are required. The feature uses existing cache configuration:

```python
DATA_CACHE_CONFIG = {
    'CACHE_TYPE': 'RedisCache',
    'CACHE_DEFAULT_TIMEOUT': 86400,
    'CACHE_KEY_PREFIX': 'superset_data_cache',
}
```

## Performance Expectations

| Scenario | Before | After |
|----------|--------|-------|
| Initial chart load | ~500ms | ~500ms (unchanged) |
| Switch to compatible viz (cache hit) | ~500ms | ~50-100ms |
| Switch to incompatible viz | ~500ms | ~500ms (fallback) |
| Cache miss | ~500ms | ~500ms (fallback) |

## Files Changed

```
superset/
├── commands/chart/data/
│   └── transform_command.py          # NEW: Transform command
├── charts/data/
│   └── api.py                         # Modified: Add /transform endpoint
├── common/
│   ├── query_object.py                # Modified: Add raw_cache_key()
│   └── query_context_processor.py     # Modified: Cache raw data
└── models/
    └── helpers.py                     # Modified: Add df_raw to QueryResult

superset-frontend/src/components/Chart/
├── chartAction.js                     # Modified: Add transform actions
└── chartReducer.ts                    # Modified: Add transform handlers
```
