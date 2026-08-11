// Wait for CDN libraries to load before executing main code
(function checkLibsAndLoad() {
  if (typeof graphologyLayout !== 'undefined' && 
      typeof graphologyLayoutForceAtlas2 !== 'undefined' &&
      typeof Sigma !== 'undefined') {
    loadGraph();
  } else {
    setTimeout(checkLibsAndLoad, 100);
  }
})();
