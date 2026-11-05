/* tiny-webapp-kit · base.js
   每个小工具站都要的那点公共 JS：日夜切换 + 复制（带 http 兜底）。
   页面里只要有一个 id="theme" 的按钮，主题就自动生效。

   三态：auto（跟随系统） → light → dark → auto …
   按钮文字显示当前态；localStorage 只存用户显式选过的态，
   选回 auto 就删掉存档，重新交给 prefers-color-scheme 决定。 */
(function(){
  var root = document.documentElement;
  var ORDER = ['auto', 'light', 'dark'];
  var LABEL = {auto:'跟随系统', light:'浅色', dark:'深色'};

  var key = document.body.getAttribute('data-theme-key') || 'ui-theme';
  var saved = localStorage.getItem(key);
  if (saved && ORDER.indexOf(saved) > -1) root.setAttribute('data-theme', saved);
  else if (!root.getAttribute('data-theme')) root.setAttribute('data-theme', 'auto');

  var btn = document.getElementById('theme');
  function paint(){
    if (!btn) return;
    var cur = root.getAttribute('data-theme') || 'auto';
    btn.textContent = LABEL[cur] || '跟随系统';
    btn.title = '主题：' + (LABEL[cur] || '跟随系统') + '（点一下换下一个）';
  }
  paint();

  if (btn){
    btn.addEventListener('click', function(){
      var cur = root.getAttribute('data-theme') || 'auto';
      var next = ORDER[(ORDER.indexOf(cur) + 1) % ORDER.length];
      root.setAttribute('data-theme', next);
      if (next === 'auto') localStorage.removeItem(key);
      else localStorage.setItem(key, next);
      paint();
    });
  }

  // 系统主题变了、而用户没手动选过，就跟着重画按钮态
  if (window.matchMedia){
    var mq = window.matchMedia('(prefers-color-scheme: dark)');
    var onChange = function(){
      if ((root.getAttribute('data-theme') || 'auto') === 'auto') paint();
    };
    if (mq.addEventListener) mq.addEventListener('change', onChange);
    else if (mq.addListener) mq.addListener(onChange);
  }

  // ---------- 复制 ----------
  // copyText('要复制的文字', 按钮元素, '原按钮文字')
  window.copyText = function(text, btn, orig){
    if (!text) return;
    var done = function(){
      if (!btn) return;
      btn.textContent = '已复制';
      setTimeout(function(){ btn.textContent = orig; }, 1200);
    };
    if (navigator.clipboard && window.isSecureContext){
      navigator.clipboard.writeText(text).then(done, fallback);
    } else { fallback(); }
    function fallback(){
      var ta = document.createElement('textarea');
      ta.value = text;
      ta.style.position = 'fixed';
      ta.style.opacity = '0';
      document.body.appendChild(ta);
      ta.select();
      try { document.execCommand('copy'); done(); } catch(e){ alert('复制失败，手动选中'); }
      document.body.removeChild(ta);
    }
  };

  // ---------- 小工具 ----------
  window.pad2 = function(n){ return n < 10 ? '0' + n : '' + n; };
  window.bytes = function(n){
    if (n < 1024) return n + ' B';
    if (n < 1048576) return (n / 1024).toFixed(1) + ' KB';
    return (n / 1048576).toFixed(1) + ' MB';
  };
})();
