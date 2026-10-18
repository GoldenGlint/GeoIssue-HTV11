import { test } from 'node:test';
import assert from 'node:assert/strict';
import { state, DEFAULT_FILTERS, shouldShowMapEmptyNotice, dismissMapEmptyNotice } from '../src/state.js';

test('empty map notice stays dismissed while panning and returns for a new search or empty episode', t => {
  const original = { filters: state.filters, dataSource: state.dataSource, panel: state.panel, mapEmptyDismissedFor: state.mapEmptyDismissedFor };
  t.after(() => Object.assign(state, original));
  Object.assign(state, { filters: { ...DEFAULT_FILTERS }, dataSource: 'pipeline', panel: null, mapEmptyDismissedFor: null });
  assert.equal(shouldShowMapEmptyNotice(0), true);
  dismissMapEmptyNotice();
  assert.equal(shouldShowMapEmptyNotice(0), false);
  assert.equal(shouldShowMapEmptyNotice(0), false); // further map movement does not reopen it
  state.filters.type = 'Flooding';
  assert.equal(shouldShowMapEmptyNotice(0), true);
  dismissMapEmptyNotice();
  state.dataSource = 'replay';
  assert.equal(shouldShowMapEmptyNotice(0), true);
  dismissMapEmptyNotice();
  assert.equal(shouldShowMapEmptyNotice(2), false);
  assert.equal(shouldShowMapEmptyNotice(0), true); // matches were visible before leaving the viewport again
  state.panel = { mode: 'multi', ids: [] };
  assert.equal(shouldShowMapEmptyNotice(0), false);
});
