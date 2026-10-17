import { test } from 'node:test';
import assert from 'node:assert/strict';
import { parseLocation, formatDms, distanceMetres, googleStreetViewUrl } from '../src/coordinates.js';

const KING_SPADINA = [-79.3953, 43.6455];
const near = (result, [lng, lat], tolerance = 0.0001) => {
  assert.ok(result.coordinates, result.error);
  assert.ok(Math.abs(result.coordinates[0] - lng) < tolerance && Math.abs(result.coordinates[1] - lat) < tolerance,
    `expected ${lat}, ${lng} but got ${result.coordinates[1]}, ${result.coordinates[0]}`);
};

test('decimal degrees in the usual forms', () => {
  for (const text of ['43.6455, -79.3953', '43.6455 -79.3953', '43.6455N 79.3953W', 'N 43.6455 W 79.3953', '43.6455 N, 79.3953 W', ' 43.6455 ,  -79.3953 ']) {
    near(parseLocation(text), KING_SPADINA);
  }
});

test('degrees, minutes and seconds with straight or curly marks', () => {
  for (const text of [`43°38'43.8"N 79°23'43.1"W`, '43°38′43.8″N, 79°23′43.1″W', '43° 38′ 43.8″ N 79° 23′ 43.1″ W', `43°38'43.8" -79°23'43.1"`, '43 38 43.8 N 79 23 43.1 W', '43 38 43.8 -79 23 43.1']) {
    near(parseLocation(text), KING_SPADINA);
  }
});

test('degrees and decimal minutes', () => {
  near(parseLocation(`43°38.730'N 79°23.718'W`), KING_SPADINA);
  near(parseLocation('43 38.730 -79 23.718'), KING_SPADINA);
});

test('a missing minus or swapped order is read sensibly and explained', () => {
  const west = parseLocation('43.6455, 79.3953');
  near(west, KING_SPADINA);
  assert.match(west.note, /west/);
  const swapped = parseLocation('-79.3953, 43.6455');
  near(swapped, KING_SPADINA);
  assert.match(swapped.note, /longitude, latitude/);
});

test('Google Maps links', () => {
  const place = 'https://www.google.com/maps/place/King+St+W+%26+Spadina+Ave,+Toronto,+ON/@43.6470,-79.3990,17z/data=!3m1!4b1!4m6!3m5!1s0x0:0x0!8m2!3d43.6455!4d-79.3953';
  near(parseLocation(place), KING_SPADINA); // the place's own position, not the camera's
  near(parseLocation('https://www.google.com/maps/@43.6455,-79.3953,3a,75y,90t/data=!3m6!1e1'), KING_SPADINA);
  near(parseLocation('https://www.google.com/maps/search/?api=1&query=43.6455%2C-79.3953'), KING_SPADINA);
  near(parseLocation('https://maps.google.com/?q=43.6455,-79.3953'), KING_SPADINA);
  near(parseLocation('google.com/maps?ll=43.6455,-79.3953&z=17'), KING_SPADINA);
  near(parseLocation(googleStreetViewUrl(KING_SPADINA)), KING_SPADINA);
  assert.equal(parseLocation(place).source, 'google_maps_link');
});

test('links that cannot be read explain what to do instead', () => {
  assert.match(parseLocation('https://maps.app.goo.gl/AbC123xyz').error, /Short share links/);
  assert.match(parseLocation('https://www.google.com/maps/place/CN+Tower').error, /right-click/);
  assert.match(parseLocation('https://example.com/?q=43.6,-79.3').error, /isn’t from Google Maps/);
});

test('rejects points outside Toronto and unreadable input', () => {
  assert.match(parseLocation('45.4215, -75.6972').error, /outside Toronto/);
  assert.match(parseLocation('hello there').error, /Couldn’t read/);
  assert.match(parseLocation('').error, /Paste/);
  assert.match(parseLocation('43 61 0 N 79 23 0 W').error, /less than 60/);
  assert.match(parseLocation('43.6455N 44.1N').error, /Both values/);
});

test('formats and measures', () => {
  assert.equal(formatDms(KING_SPADINA), '43°38′43.8″N 79°23′43.1″W');
  assert.ok(Math.abs(distanceMetres([-79.3953, 43.6455], [-79.3953, 43.6465]) - 111.2) < 0.5);
});
