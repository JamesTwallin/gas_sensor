// react-native-ble-plx's plugin, with neverForLocation on, declares the two
// location permissions a second time as <uses-permission-sdk-23> capped at
// maxSdkVersion 30 (old phones need location to scan for Bluetooth). This app
// also needs location on every Android version, to tag readings, so the
// manifest ends up with both a capped and an uncapped declaration and Play
// Console rejects the upload ("duplicate declarations ... with different
// maxSdkVersions"). The uncapped one covers the old phones too, so drop the
// capped copies.
//
// Must be listed BEFORE react-native-ble-plx in app.json: manifest mods run in
// reverse order of the plugins list, and this has to run after theirs.
const { withAndroidManifest } = require('expo/config-plugins');

const LOCATION = [
  'android.permission.ACCESS_COARSE_LOCATION',
  'android.permission.ACCESS_FINE_LOCATION',
];

module.exports = function withSingleLocationPermission(config) {
  return withAndroidManifest(config, (c) => {
    const manifest = c.modResults.manifest;
    const sdk23 = manifest['uses-permission-sdk-23'];
    if (Array.isArray(sdk23)) {
      manifest['uses-permission-sdk-23'] = sdk23.filter(
        (p) => !LOCATION.includes(p.$['android:name']),
      );
    }
    return c;
  });
};
