/* Blind World Hub: the world drawn as raised dots, like braille, turning slowly. WebGL, about 6 KB, no library.
   It starts only after the page is ready, never blocks reading, stops when it is off screen, and stays still when
   the device asks for reduced motion or when 3D effects are turned off in Display settings. */
(function () {
  "use strict";
  var canvas = document.getElementById("globe");
  if (!canvas) return;
  /* Land map: 180 by 90 cells of 2 degrees, from Natural Earth (public domain), one bit per cell. */
  var MASK = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAOAfAP8DAAAAAAAAAAAAAAAAAAAAAADo//z//wcAAAAAAAACAAAAAAAAAAAAhvvw//8PAPABAAAAwAMAAAAAAAAAwADkw////wEABAAAAABgAAAAAAAAAADAUT8A/v8PAAAAAAwA/j8AuAEAAAAAcBHtDcD/fwAAAAAwAPz/fwMAABCAAQD5w/wD8P8FAAAMAIL7//9//xOAAP/ff0668QD/HwAA+A8At///////v3/w/////x8++B8AAOD/1//7////////jP////+/+AE/gAcAn9f//////////w/w/////wEs4AEAAHz+////////////gL////8HeAAcAADg5///////////9ADgAf7/f4AnAAAAAH78////////H0QAAAiA//8f8AcAAIBB4////////38ADwAQAOD//5//AQAAHAT/////////A3AAAAAA/v//+T8AAGDz//////////8DAQAAAMD/////AwAAsP//////////LwAAAAAA6P///2IAAAD+//////////8CAAAAAAD///8/CAAA4P//////////JwAAAAAA8P///wYAAAD+/un//////z8AAAAAAAD///8HAAAA/pgP/P//////MQAAAAAA8P//PwAAAMBD9v7//////wcBAAAAAAD///8AAAAAPkD7//////8hEAAAAAAA4P//DwAAAIDhAv//////f8YAAAAAAAD8//8AAAAA+AdE//////8jDwAAAAAAgP//AwAAAMD/APD/////PxgAAAAAAADw/x8AAAAA/n/v//////8HAAAAAAAAAPwDAgAAAOD////7////fwAAAAAAAACgHyAAAACA//9/f/7///8DAAAAAAAAAPQBAAAAAPj//+cv+P//PwAAAAAAAAAAHjAAAADA/////g/+//8EAAAAAAAAAOBhCAAAAP7//99/4D//AAAAAAAAAAAAPAMEAADA////+Qf84BcAAAAAAAAAAAA/AAAAAPz//58fgAf+QAAAAAAAAAAAAA8AAADg////ewA4gA8EAAAAAAAAAADAAAAAAPz//38BgAP4QQAAAAAAAAAAAAgPAADA////zwAwgAwQAAAAAAAAAAAA9Q8AAPj///8HAAVIAAAAAAAAAAAAAID/AQAA////fwBAAAAQAAAAAAAAAAAA+P8AAGDh//8DAAA0GAAAAAAAAAAAAID/HwAAAPj/HwAAgMIBAAAAAAAAAAAA/P8BAACA//8AAAAYXgAAAAAAAAAAAMD/fwAAAPz/BwAAAOOBAQAAAAAAAAAA/P8/AACA/z8AAABgbtQBAAAAAAAAAOD//w8AAPD/AwAAAAQIeAAAAAAAAAAA/P//AQAA/z8AAACAA4APAQAAAAAAAID//w8AAPD/AwAAAAARsEAAAAAAAAAA+P9/AAAA/j8AAAAAAAAAAAAAAAAAAAD//wcAAPD/QwAAAACAIwAAAAAAAAAA8P9/AAAA/z8EAAAAAD8GIAAAAAAAAAD8/wMAAPD/cQAAAAD4ZwAAAAAAAAAAgP8/AAAA/w8HAAAAgP8HAAAAAAAAAAD4/wMAAOD/MAAAAAD//wEBAAAAAAAAgP8PAAAA/g8DAAAA+P8fAAAAAAAAAAD4PwAAAOB/EAAAAID//wMAAAAAAAAAgP8DAAAA/AMAAAAA+P9/AAAAAAAAAAD8HwAAAMA/AAAAAID//wcAAAAAAAAAwP8BAAAA+AEAAAAA8P9/AAAAAAAAAAD8DwAAAIAPAAAAAAAP/gMAAAAAAAAAwB8AAAAAAAAAAAAAEIAfAAEAAAAAAAD+AwAAAAAAAAAAAAAA8AEgAAAAAAAA4AcAAAAAAAAAAAAAAAAAAAYAAAAAAABeAAAAAAAAAAAAAAAAwAAwAAAAAAAAwAMAAAAAAAAAAAAAAAAIgAEAAAAAAAAeAAAAAAAAAAAAAAAAAAAMAAAAAAAA4AEAAAAAAAAAAAAAAAAAAAAAAAAAAAAPAAAAAAAAAAABAAAAAAAAAAAAAAAAcAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAOAAAAAAAAAAAAAAAAAAAAAAAAAAAAwAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAABAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAMAAAAAAAB4AEDwn/8HAAAAAAAAAAAwAAAAAACA/P/h/////w8AAAAAAAAAwAcAAAD4////z///////PwAAAAAAHALwAACA//////////////8HAADw/y///wMAAP7/////////////HwAA+P///38AAID///////////////8AAPL/////BwAO////////////////DwAA8P////8HEPD//////////////z8AAOD/////////////////////////H/AfwP//////////////////////////////////////////////////////////////////////////////////////";

  function start() {
    var gl = canvas.getContext("webgl", { antialias: true, alpha: true, premultipliedAlpha: true });
    if (!gl) return;
    var bin = atob(MASK), bits = new Uint8Array(bin.length);
    for (var i = 0; i < bin.length; i++) bits[i] = bin.charCodeAt(i);
    function land(lat, lon) {
      var x = Math.min(179, Math.max(0, Math.floor((lon + 180) / 2)));
      var y = Math.min(89, Math.max(0, Math.floor((90 - lat) / 2)));
      var k = y * 180 + x;
      return (bits[k >> 3] >> (k & 7)) & 1;
    }
    var pts = [], N = 5200, golden = Math.PI * (3 - Math.sqrt(5));
    for (var n = 0; n < N; n++) {
      var yv = 1 - (n / (N - 1)) * 2, r = Math.sqrt(1 - yv * yv), th = golden * n;
      var x3 = Math.cos(th) * r, z3 = Math.sin(th) * r;
      var lat = Math.asin(yv) * 180 / Math.PI, lon = Math.atan2(z3, x3) * 180 / Math.PI;
      if (land(lat, lon)) pts.push(x3, yv, z3, 1);
      else if (n % 4 === 0) pts.push(x3, yv, z3, 0);
    }
    for (var m = 0; m < 160; m++) {                  /* a ring of dots around the world, the hub */
      var a = m / 160 * Math.PI * 2;
      pts.push(Math.cos(a) * 1.28, 0, Math.sin(a) * 1.28, 2);
    }
    var data = new Float32Array(pts), count = pts.length / 4;

    var vs = "attribute vec4 p;uniform float rot,tilt,ring,px,aspect;varying float d;varying float k;" +
      "void main(){vec3 v=p.xyz;float ry=p.w>1.5?ring:rot;float c=cos(ry),s=sin(ry);v=vec3(c*v.x+s*v.z,v.y,-s*v.x+c*v.z);" +
      "float t=p.w>1.5?tilt+0.42:tilt;float ct=cos(t),st=sin(t);v=vec3(v.x,ct*v.y-st*v.z,st*v.y+ct*v.z);" +
      "d=(v.z+1.3)/2.6;k=p.w;gl_Position=vec4(v.x*0.72/aspect,v.y*0.72,-v.z*0.5,1.0);" +
      "gl_PointSize=px*(k>1.5?0.55:(k>0.5?1.0:0.62))*(0.45+0.75*d);}";
    var fs = "precision mediump float;varying float d;varying float k;" +
      "void main(){vec2 c=gl_PointCoord*2.0-1.0;float r=dot(c,c);if(r>1.0)discard;" +
      "vec3 n=normalize(vec3(c.x,-c.y,sqrt(1.0-r)));float l=clamp(dot(n,normalize(vec3(-0.45,0.55,0.75))),0.0,1.0);" +
      "vec3 gold=vec3(1.0,0.78,0.17),cream=vec3(1.0,0.96,0.82),sea=vec3(0.42,0.58,0.86);" +
      "vec3 col=k>1.5?cream:(k>0.5?mix(gold*0.55,cream,pow(l,3.0))*(0.35+0.9*l):sea*(0.5+0.5*l));" +
      "float a=(k>1.5?0.55:(k>0.5?1.0:0.32))*smoothstep(1.0,0.72,r)*(0.18+0.82*d);gl_FragColor=vec4(col*a,a);}";
    function sh(type, src) {
      var s = gl.createShader(type); gl.shaderSource(s, src); gl.compileShader(s);
      return gl.getShaderParameter(s, gl.COMPILE_STATUS) ? s : null;
    }
    var prog = gl.createProgram(), v1 = sh(gl.VERTEX_SHADER, vs), f1 = sh(gl.FRAGMENT_SHADER, fs);
    if (!v1 || !f1) return;
    gl.attachShader(prog, v1); gl.attachShader(prog, f1); gl.linkProgram(prog);
    if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) return;
    gl.useProgram(prog);
    var buf = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buf);
    gl.bufferData(gl.ARRAY_BUFFER, data, gl.STATIC_DRAW);
    var loc = gl.getAttribLocation(prog, "p");
    gl.enableVertexAttribArray(loc);
    gl.vertexAttribPointer(loc, 4, gl.FLOAT, false, 0, 0);
    var U = {};
    ["rot", "tilt", "ring", "px", "aspect"].forEach(function (u) { U[u] = gl.getUniformLocation(prog, u); });
    gl.enable(gl.BLEND); gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA);
    gl.enable(gl.DEPTH_TEST); gl.depthFunc(gl.LEQUAL);

    var rot = 1.25, tilt = 0.32, ring = 0, targetTilt = 0.32, last = 0, running = false, visible = true;
    function size() {
      var dpr = Math.min(window.devicePixelRatio || 1, 2), w = canvas.clientWidth || 300, h = canvas.clientHeight || 300;
      canvas.width = Math.round(w * dpr); canvas.height = Math.round(h * dpr);
      gl.viewport(0, 0, canvas.width, canvas.height);
      gl.uniform1f(U.aspect, canvas.width / canvas.height);
      gl.uniform1f(U.px, Math.max(2.2, canvas.height / 118));
    }
    function draw() {
      gl.clearColor(0, 0, 0, 0);
      gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
      gl.uniform1f(U.rot, rot); gl.uniform1f(U.tilt, tilt); gl.uniform1f(U.ring, ring);
      gl.drawArrays(gl.POINTS, 0, count);
    }
    function still() { return !(window.BWH ? window.BWH.motionOn() : true) || (window.BWH && window.BWH.reduceMotion()); }
    function frame(t) {
      if (!running) return;
      var dt = last ? Math.min(0.05, (t - last) / 1000) : 0;
      last = t;
      rot += dt * 0.16; ring -= dt * 0.1; tilt += (targetTilt - tilt) * Math.min(1, dt * 2.5);
      draw();
      requestAnimationFrame(frame);
    }
    function play() {
      if (running || still() || !visible || document.hidden) return;
      running = true; last = 0; requestAnimationFrame(frame);
    }
    function pause() { running = false; }
    size(); draw(); canvas.classList.add("ready");
    play();
    window.addEventListener("resize", function () { size(); draw(); });
    document.addEventListener("visibilitychange", function () { if (document.hidden) pause(); else play(); });
    document.addEventListener("bwh-motion", function (e) { if (e.detail) { size(); draw(); play(); } else pause(); });
    if ("IntersectionObserver" in window) {
      new IntersectionObserver(function (es) { visible = es[0].isIntersecting; if (visible) play(); else pause(); }).observe(canvas);
    }
    window.addEventListener("pointermove", function (e) {
      targetTilt = 0.32 + ((e.clientY / window.innerHeight) - 0.5) * 0.35;
    }, { passive: true });
  }
  function later() {
    if ("requestIdleCallback" in window) requestIdleCallback(start, { timeout: 1200 }); else setTimeout(start, 200);
  }
  if (document.readyState === "complete") later(); else window.addEventListener("load", later);
})();
