"use strict";(this.webpackChunkDocsMarkdownEditor=this.webpackChunkDocsMarkdownEditor||[]).push([[802],{4101(t,e,s){function i(t,e,s,i){var n,o=arguments.length,r=o<3?e:null===i?i=Object.getOwnPropertyDescriptor(e,s):i;if("object"==typeof Reflect&&"function"==typeof Reflect.decorate)r=Reflect.decorate(t,e,s,i);else for(var l=t.length-1;l>=0;l--)(n=t[l])&&(r=(o<3?n(r):o>3?n(e,s,r):n(e,s))||r);return o>3&&r&&Object.defineProperty(e,s,r),r}s.r(e),s.d(e,{Modal:()=>Ot}),Object.create,Object.create;const n=function(){if("undefined"!=typeof globalThis)return globalThis;if(void 0!==s.g)return s.g;if("undefined"!=typeof self)return self;if("undefined"!=typeof window)return window;try{return new Function("return this")()}catch(t){return{}}}();void 0===n.trustedTypes&&(n.trustedTypes={createPolicy:(t,e)=>e});const o={configurable:!1,enumerable:!1,writable:!1};void 0===n.FAST&&Reflect.defineProperty(n,"FAST",Object.assign({value:Object.create(null)},o));const r=n.FAST;if(void 0===r.getById){const t=Object.create(null);Reflect.defineProperty(r,"getById",Object.assign({value(e,s){let i=t[e];return void 0===i&&(i=s?t[e]=s():null),i}},o))}function l(){const t=new WeakMap;return function(e){let s=t.get(e);if(void 0===s){let i=Reflect.getPrototypeOf(e);for(;void 0===s&&null!==i;)s=t.get(i),i=Reflect.getPrototypeOf(i);s=void 0===s?[]:s.slice(0),t.set(e,s)}return s}}Object.freeze([]);const a=n.FAST.getById(1,()=>{const t=[],e=[];function s(){if(e.length)throw e.shift()}function i(t){try{t.call()}catch(t){e.push(t),setTimeout(s,0)}}function o(){let e=0;for(;e<t.length;)if(i(t[e]),e++,e>1024){for(let s=0,i=t.length-e;s<i;s++)t[s]=t[s+e];t.length-=e,e=0}t.length=0}return Object.freeze({enqueue:function(e){t.length<1&&n.requestAnimationFrame(o),t.push(e)},process:o})}),c=n.trustedTypes.createPolicy("fast-html",{createHTML:t=>t});let h=c;const d=`fast-${Math.random().toString(36).substring(2,8)}`,u=`${d}{`,f=`}${d}`,b=Object.freeze({supportsAdoptedStyleSheets:Array.isArray(document.adoptedStyleSheets)&&"replace"in CSSStyleSheet.prototype,setHTMLPolicy(t){if(h!==c)throw new Error("The HTML policy can only be set once.");h=t},createHTML:t=>h.createHTML(t),isMarker:t=>t&&8===t.nodeType&&t.data.startsWith(d),extractDirectiveIndexFromMarker:t=>parseInt(t.data.replace(`${d}:`,"")),createInterpolationPlaceholder:t=>`${u}${t}${f}`,createCustomAttributePlaceholder(t,e){return`${t}="${this.createInterpolationPlaceholder(e)}"`},createBlockPlaceholder:t=>`\x3c!--${d}:${t}--\x3e`,queueUpdate:a.enqueue,processUpdates:a.process,nextUpdate:()=>new Promise(a.enqueue),setAttribute(t,e,s){null==s?t.removeAttribute(e):t.setAttribute(e,s)},setBooleanAttribute(t,e,s){s?t.setAttribute(e,""):t.removeAttribute(e)},removeChildNodes(t){for(let e=t.firstChild;null!==e;e=t.firstChild)t.removeChild(e)},createTemplateWalker:t=>document.createTreeWalker(t,133,null,!1)});class p{constructor(t,e){this.sub1=void 0,this.sub2=void 0,this.spillover=void 0,this.source=t,this.sub1=e}has(t){return void 0===this.spillover?this.sub1===t||this.sub2===t:-1!==this.spillover.indexOf(t)}subscribe(t){const e=this.spillover;if(void 0===e){if(this.has(t))return;if(void 0===this.sub1)return void(this.sub1=t);if(void 0===this.sub2)return void(this.sub2=t);this.spillover=[this.sub1,this.sub2,t],this.sub1=void 0,this.sub2=void 0}else-1===e.indexOf(t)&&e.push(t)}unsubscribe(t){const e=this.spillover;if(void 0===e)this.sub1===t?this.sub1=void 0:this.sub2===t&&(this.sub2=void 0);else{const s=e.indexOf(t);-1!==s&&e.splice(s,1)}}notify(t){const e=this.spillover,s=this.source;if(void 0===e){const e=this.sub1,i=this.sub2;void 0!==e&&e.handleChange(s,t),void 0!==i&&i.handleChange(s,t)}else for(let i=0,n=e.length;i<n;++i)e[i].handleChange(s,t)}}class m{constructor(t){this.subscribers={},this.sourceSubscribers=null,this.source=t}notify(t){var e;const s=this.subscribers[t];void 0!==s&&s.notify(t),null===(e=this.sourceSubscribers)||void 0===e||e.notify(t)}subscribe(t,e){var s;if(e){let s=this.subscribers[e];void 0===s&&(this.subscribers[e]=s=new p(this.source)),s.subscribe(t)}else this.sourceSubscribers=null!==(s=this.sourceSubscribers)&&void 0!==s?s:new p(this.source),this.sourceSubscribers.subscribe(t)}unsubscribe(t,e){var s;if(e){const s=this.subscribers[e];void 0!==s&&s.unsubscribe(t)}else null===(s=this.sourceSubscribers)||void 0===s||s.unsubscribe(t)}}const g=r.getById(2,()=>{const t=/(:|&&|\|\||if)/,e=new WeakMap,s=b.queueUpdate;let i,n=t=>{throw new Error("Must call enableArrayObservation before observing arrays.")};function o(t){let s=t.$fastController||e.get(t);return void 0===s&&(Array.isArray(t)?s=n(t):e.set(t,s=new m(t))),s}const r=l();class a{constructor(t){this.name=t,this.field=`_${t}`,this.callback=`${t}Changed`}getValue(t){return void 0!==i&&i.watch(t,this.name),t[this.field]}setValue(t,e){const s=this.field,i=t[s];if(i!==e){t[s]=e;const n=t[this.callback];"function"==typeof n&&n.call(t,i,e),o(t).notify(this.name)}}}class c extends p{constructor(t,e,s=!1){super(t,e),this.binding=t,this.isVolatileBinding=s,this.needsRefresh=!0,this.needsQueue=!0,this.first=this,this.last=null,this.propertySource=void 0,this.propertyName=void 0,this.notifier=void 0,this.next=void 0}observe(t,e){this.needsRefresh&&null!==this.last&&this.disconnect();const s=i;i=this.needsRefresh?this:void 0,this.needsRefresh=this.isVolatileBinding;const n=this.binding(t,e);return i=s,n}disconnect(){if(null!==this.last){let t=this.first;for(;void 0!==t;)t.notifier.unsubscribe(this,t.propertyName),t=t.next;this.last=null,this.needsRefresh=this.needsQueue=!0}}watch(t,e){const s=this.last,n=o(t),r=null===s?this.first:{};if(r.propertySource=t,r.propertyName=e,r.notifier=n,n.subscribe(this,e),null!==s){if(!this.needsRefresh){let e;i=void 0,e=s.propertySource[s.propertyName],i=this,t===e&&(this.needsRefresh=!0)}s.next=r}this.last=r}handleChange(){this.needsQueue&&(this.needsQueue=!1,s(this))}call(){null!==this.last&&(this.needsQueue=!0,this.notify(this))}records(){let t=this.first;return{next:()=>{const e=t;return void 0===e?{value:void 0,done:!0}:(t=t.next,{value:e,done:!1})},[Symbol.iterator]:function(){return this}}}}return Object.freeze({setArrayObserverFactory(t){n=t},getNotifier:o,track(t,e){void 0!==i&&i.watch(t,e)},trackVolatile(){void 0!==i&&(i.needsRefresh=!0)},notify(t,e){o(t).notify(e)},defineProperty(t,e){"string"==typeof e&&(e=new a(e)),r(t).push(e),Reflect.defineProperty(t,e.name,{enumerable:!0,get:function(){return e.getValue(this)},set:function(t){e.setValue(this,t)}})},getAccessors:r,binding(t,e,s=this.isVolatileBinding(t)){return new c(t,e,s)},isVolatileBinding:e=>t.test(e.toString())})});function v(t,e){g.defineProperty(t,e)}const y=r.getById(3,()=>{let t=null;return{get:()=>t,set(e){t=e}}});class S{constructor(){this.index=0,this.length=0,this.parent=null,this.parentContext=null}get event(){return y.get()}get isEven(){return this.index%2==0}get isOdd(){return this.index%2!=0}get isFirst(){return 0===this.index}get isInMiddle(){return!this.isFirst&&!this.isLast}get isLast(){return this.index===this.length-1}static setEvent(t){y.set(t)}}g.defineProperty(S.prototype,"index"),g.defineProperty(S.prototype,"length");const w=Object.seal(new S);class C{constructor(){this.targetIndex=0}}class x extends C{constructor(){super(...arguments),this.createPlaceholder=b.createInterpolationPlaceholder}}function T(t,e){this.source=t,this.context=e,null===this.bindingObserver&&(this.bindingObserver=g.binding(this.binding,this,this.isBindingVolatile)),this.updateTarget(this.bindingObserver.observe(t,e))}function k(t,e){this.source=t,this.context=e,this.target.addEventListener(this.targetName,this)}function O(){this.bindingObserver.disconnect(),this.source=null,this.context=null}function B(){this.bindingObserver.disconnect(),this.source=null,this.context=null;const t=this.target.$fastView;void 0!==t&&t.isComposed&&(t.unbind(),t.needsBindOnly=!0)}function A(){this.target.removeEventListener(this.targetName,this),this.source=null,this.context=null}function E(t){b.setAttribute(this.target,this.targetName,t)}function N(t){b.setBooleanAttribute(this.target,this.targetName,t)}function $(t){if(null==t&&(t=""),t.create){this.target.textContent="";let e=this.target.$fastView;void 0===e?e=t.create():this.target.$fastTemplate!==t&&(e.isComposed&&(e.remove(),e.unbind()),e=t.create()),e.isComposed?e.needsBindOnly&&(e.needsBindOnly=!1,e.bind(this.source,this.context)):(e.isComposed=!0,e.bind(this.source,this.context),e.insertBefore(this.target),this.target.$fastView=e,this.target.$fastTemplate=t)}else{const e=this.target.$fastView;void 0!==e&&e.isComposed&&(e.isComposed=!1,e.remove(),e.needsBindOnly?e.needsBindOnly=!1:e.unbind()),this.target.textContent=t}}function F(t){this.target[this.targetName]=t}function _(t){const e=this.classVersions||Object.create(null),s=this.target;let i=this.version||0;if(null!=t&&t.length){const n=t.split(/\s+/);for(let t=0,o=n.length;t<o;++t){const o=n[t];""!==o&&(e[o]=i,s.classList.add(o))}}if(this.classVersions=e,this.version=i+1,0!==i){i-=1;for(const t in e)e[t]===i&&s.classList.remove(t)}}class M extends x{constructor(t){super(),this.binding=t,this.bind=T,this.unbind=O,this.updateTarget=E,this.isBindingVolatile=g.isVolatileBinding(this.binding)}get targetName(){return this.originalTargetName}set targetName(t){if(this.originalTargetName=t,void 0!==t)switch(t[0]){case":":if(this.cleanedTargetName=t.substr(1),this.updateTarget=F,"innerHTML"===this.cleanedTargetName){const t=this.binding;this.binding=(e,s)=>b.createHTML(t(e,s))}break;case"?":this.cleanedTargetName=t.substr(1),this.updateTarget=N;break;case"@":this.cleanedTargetName=t.substr(1),this.bind=k,this.unbind=A;break;default:this.cleanedTargetName=t,"class"===t&&(this.updateTarget=_)}}targetAtContent(){this.updateTarget=$,this.unbind=B}createBehavior(t){return new V(t,this.binding,this.isBindingVolatile,this.bind,this.unbind,this.updateTarget,this.cleanedTargetName)}}class V{constructor(t,e,s,i,n,o,r){this.source=null,this.context=null,this.bindingObserver=null,this.target=t,this.binding=e,this.isBindingVolatile=s,this.bind=i,this.unbind=n,this.updateTarget=o,this.targetName=r}handleChange(){this.updateTarget(this.bindingObserver.observe(this.source,this.context))}handleEvent(t){S.setEvent(t);const e=this.binding(this.source,this.context);S.setEvent(null),!0!==e&&t.preventDefault()}}let L=null;class I{addFactory(t){t.targetIndex=this.targetIndex,this.behaviorFactories.push(t)}captureContentBinding(t){t.targetAtContent(),this.addFactory(t)}reset(){this.behaviorFactories=[],this.targetIndex=-1}release(){L=this}static borrow(t){const e=L||new I;return e.directives=t,e.reset(),L=null,e}}function j(t){if(1===t.length)return t[0];let e;const s=t.length,i=t.map(t=>"string"==typeof t?()=>t:(e=t.targetName||e,t.binding)),n=new M((t,e)=>{let n="";for(let o=0;o<s;++o)n+=i[o](t,e);return n});return n.targetName=e,n}const H=f.length;function P(t,e){const s=e.split(u);if(1===s.length)return null;const i=[];for(let e=0,n=s.length;e<n;++e){const n=s[e],o=n.indexOf(f);let r;if(-1===o)r=n;else{const e=parseInt(n.substring(0,o));i.push(t.directives[e]),r=n.substring(o+H)}""!==r&&i.push(r)}return i}function R(t,e,s=!1){const i=e.attributes;for(let n=0,o=i.length;n<o;++n){const r=i[n],l=r.value,a=P(t,l);let c=null;null===a?s&&(c=new M(()=>l),c.targetName=r.name):c=j(a),null!==c&&(e.removeAttributeNode(r),n--,o--,t.addFactory(c))}}function z(t,e,s){const i=P(t,e.textContent);if(null!==i){let n=e;for(let o=0,r=i.length;o<r;++o){const r=i[o],l=0===o?e:n.parentNode.insertBefore(document.createTextNode(""),n.nextSibling);"string"==typeof r?l.textContent=r:(l.textContent=" ",t.captureContentBinding(r)),n=l,t.targetIndex++,l!==e&&s.nextNode()}t.targetIndex--}}const D=document.createRange();class q{constructor(t,e){this.fragment=t,this.behaviors=e,this.source=null,this.context=null,this.firstChild=t.firstChild,this.lastChild=t.lastChild}appendTo(t){t.appendChild(this.fragment)}insertBefore(t){if(this.fragment.hasChildNodes())t.parentNode.insertBefore(this.fragment,t);else{const e=this.lastChild;if(t.previousSibling===e)return;const s=t.parentNode;let i,n=this.firstChild;for(;n!==e;)i=n.nextSibling,s.insertBefore(n,t),n=i;s.insertBefore(e,t)}}remove(){const t=this.fragment,e=this.lastChild;let s,i=this.firstChild;for(;i!==e;)s=i.nextSibling,t.appendChild(i),i=s;t.appendChild(e)}dispose(){const t=this.firstChild.parentNode,e=this.lastChild;let s,i=this.firstChild;for(;i!==e;)s=i.nextSibling,t.removeChild(i),i=s;t.removeChild(e);const n=this.behaviors,o=this.source;for(let t=0,e=n.length;t<e;++t)n[t].unbind(o)}bind(t,e){const s=this.behaviors;if(this.source!==t)if(null!==this.source){const i=this.source;this.source=t,this.context=e;for(let n=0,o=s.length;n<o;++n){const o=s[n];o.unbind(i),o.bind(t,e)}}else{this.source=t,this.context=e;for(let i=0,n=s.length;i<n;++i)s[i].bind(t,e)}}unbind(){if(null===this.source)return;const t=this.behaviors,e=this.source;for(let s=0,i=t.length;s<i;++s)t[s].unbind(e);this.source=null}static disposeContiguousBatch(t){if(0!==t.length){D.setStartBefore(t[0].firstChild),D.setEndAfter(t[t.length-1].lastChild),D.deleteContents();for(let e=0,s=t.length;e<s;++e){const s=t[e],i=s.behaviors,n=s.source;for(let t=0,e=i.length;t<e;++t)i[t].unbind(n)}}}}class W{constructor(t,e){this.behaviorCount=0,this.hasHostBehaviors=!1,this.fragment=null,this.targetOffset=0,this.viewBehaviorFactories=null,this.hostBehaviorFactories=null,this.html=t,this.directives=e}create(t){if(null===this.fragment){let t;const e=this.html;if("string"==typeof e){t=document.createElement("template"),t.innerHTML=b.createHTML(e);const s=t.content.firstElementChild;null!==s&&"TEMPLATE"===s.tagName&&(t=s)}else t=e;const s=function(t,e){const s=t.content;document.adoptNode(s);const i=I.borrow(e);R(i,t,!0);const n=i.behaviorFactories;i.reset();const o=b.createTemplateWalker(s);let r;for(;r=o.nextNode();)switch(i.targetIndex++,r.nodeType){case 1:R(i,r);break;case 3:z(i,r,o);break;case 8:b.isMarker(r)&&i.addFactory(e[b.extractDirectiveIndexFromMarker(r)])}let l=0;(b.isMarker(s.firstChild)||1===s.childNodes.length&&e.length)&&(s.insertBefore(document.createComment(""),s.firstChild),l=-1);const a=i.behaviorFactories;return i.release(),{fragment:s,viewBehaviorFactories:a,hostBehaviorFactories:n,targetOffset:l}}(t,this.directives);this.fragment=s.fragment,this.viewBehaviorFactories=s.viewBehaviorFactories,this.hostBehaviorFactories=s.hostBehaviorFactories,this.targetOffset=s.targetOffset,this.behaviorCount=this.viewBehaviorFactories.length+this.hostBehaviorFactories.length,this.hasHostBehaviors=this.hostBehaviorFactories.length>0}const e=this.fragment.cloneNode(!0),s=this.viewBehaviorFactories,i=new Array(this.behaviorCount),n=b.createTemplateWalker(e);let o=0,r=this.targetOffset,l=n.nextNode();for(let t=s.length;o<t;++o){const t=s[o],e=t.targetIndex;for(;null!==l;){if(r===e){i[o]=t.createBehavior(l);break}l=n.nextNode(),r++}}if(this.hasHostBehaviors){const e=this.hostBehaviorFactories;for(let s=0,n=e.length;s<n;++s,++o)i[o]=e[s].createBehavior(t)}return new q(e,i)}render(t,e,s){"string"==typeof e&&(e=document.getElementById(e)),void 0===s&&(s=e);const i=this.create(s);return i.bind(t,w),i.appendTo(e),i}}const U=/([ \x09\x0a\x0c\x0d])([^\0-\x1F\x7F-\x9F "'>=/]+)([ \x09\x0a\x0c\x0d]*=[ \x09\x0a\x0c\x0d]*(?:[^ \x09\x0a\x0c\x0d"'`<>=]*|"[^"]*|'[^']*))$/;function Q(t,...e){const s=[];let i="";for(let n=0,o=t.length-1;n<o;++n){const o=t[n];let r=e[n];if(i+=o,r instanceof W){const t=r;r=()=>t}if("function"==typeof r&&(r=new M(r)),r instanceof x){const t=U.exec(o);null!==t&&(r.targetName=t[2])}r instanceof C?(i+=r.createPlaceholder(s.length),s.push(r)):i+=r}return i+=t[t.length-1],new W(i,s)}const J=t=>"function"==typeof t,K=()=>null;function Y(t){return void 0===t?K:J(t)?t:()=>t}function G(t,e,s){const i=J(t)?t:()=>t,n=Y(e),o=Y(s);return(t,e)=>i(t,e)?n(t,e):o(t,e)}class X{constructor(){this.targets=new WeakSet}addStylesTo(t){this.targets.add(t)}removeStylesFrom(t){this.targets.delete(t)}isAttachedTo(t){return this.targets.has(t)}withBehaviors(...t){return this.behaviors=null===this.behaviors?t:this.behaviors.concat(t),this}}function Z(t){return t.map(t=>t instanceof X?Z(t.styles):[t]).reduce((t,e)=>t.concat(e),[])}function tt(t){return t.map(t=>t instanceof X?t.behaviors:null).reduce((t,e)=>null===e?t:(null===t&&(t=[]),t.concat(e)),null)}X.create=(()=>{if(b.supportsAdoptedStyleSheets){const t=new Map;return e=>new it(e,t)}return t=>new ot(t)})();let et=(t,e)=>{t.adoptedStyleSheets=[...t.adoptedStyleSheets,...e]},st=(t,e)=>{t.adoptedStyleSheets=t.adoptedStyleSheets.filter(t=>-1===e.indexOf(t))};if(b.supportsAdoptedStyleSheets)try{document.adoptedStyleSheets.push(),document.adoptedStyleSheets.splice(),et=(t,e)=>{t.adoptedStyleSheets.push(...e)},st=(t,e)=>{for(const s of e){const e=t.adoptedStyleSheets.indexOf(s);-1!==e&&t.adoptedStyleSheets.splice(e,1)}}}catch(t){}class it extends X{constructor(t,e){super(),this.styles=t,this.styleSheetCache=e,this._styleSheets=void 0,this.behaviors=tt(t)}get styleSheets(){if(void 0===this._styleSheets){const t=this.styles,e=this.styleSheetCache;this._styleSheets=Z(t).map(t=>{if(t instanceof CSSStyleSheet)return t;let s=e.get(t);return void 0===s&&(s=new CSSStyleSheet,s.replaceSync(t),e.set(t,s)),s})}return this._styleSheets}addStylesTo(t){et(t,this.styleSheets),super.addStylesTo(t)}removeStylesFrom(t){st(t,this.styleSheets),super.removeStylesFrom(t)}}let nt=0;class ot extends X{constructor(t){super(),this.styles=t,this.behaviors=null,this.behaviors=tt(t),this.styleSheets=Z(t),this.styleClass="fast-style-class-"+ ++nt}addStylesTo(t){const e=this.styleSheets,s=this.styleClass;t=this.normalizeTarget(t);for(let i=0;i<e.length;i++){const n=document.createElement("style");n.innerHTML=e[i],n.className=s,t.append(n)}super.addStylesTo(t)}removeStylesFrom(t){const e=(t=this.normalizeTarget(t)).querySelectorAll(`.${this.styleClass}`);for(let s=0,i=e.length;s<i;++s)t.removeChild(e[s]);super.removeStylesFrom(t)}isAttachedTo(t){return super.isAttachedTo(this.normalizeTarget(t))}normalizeTarget(t){return t===document?document.body:t}}const rt=Object.freeze({locate:l()}),lt={toView:t=>t?"true":"false",fromView:t=>null!=t&&"false"!==t&&!1!==t&&0!==t};class at{constructor(t,e,s=e.toLowerCase(),i="reflect",n){this.guards=new Set,this.Owner=t,this.name=e,this.attribute=s,this.mode=i,this.converter=n,this.fieldName=`_${e}`,this.callbackName=`${e}Changed`,this.hasCallback=this.callbackName in t.prototype,"boolean"===i&&void 0===n&&(this.converter=lt)}setValue(t,e){const s=t[this.fieldName],i=this.converter;void 0!==i&&(e=i.fromView(e)),s!==e&&(t[this.fieldName]=e,this.tryReflectToAttribute(t),this.hasCallback&&t[this.callbackName](s,e),t.$fastController.notify(this.name))}getValue(t){return g.track(t,this.name),t[this.fieldName]}onAttributeChangedCallback(t,e){this.guards.has(t)||(this.guards.add(t),this.setValue(t,e),this.guards.delete(t))}tryReflectToAttribute(t){const e=this.mode,s=this.guards;s.has(t)||"fromView"===e||b.queueUpdate(()=>{s.add(t);const i=t[this.fieldName];switch(e){case"reflect":const e=this.converter;b.setAttribute(t,this.attribute,void 0!==e?e.toView(i):i);break;case"boolean":b.setBooleanAttribute(t,this.attribute,i)}s.delete(t)})}static collect(t,...e){const s=[];e.push(rt.locate(t));for(let i=0,n=e.length;i<n;++i){const n=e[i];if(void 0!==n)for(let e=0,i=n.length;e<i;++e){const i=n[e];"string"==typeof i?s.push(new at(t,i)):s.push(new at(t,i.property,i.attribute,i.mode,i.converter))}}return s}}const ct={mode:"open"},ht={},dt=r.getById(4,()=>{const t=new Map;return Object.freeze({register:e=>!t.has(e.type)&&(t.set(e.type,e),!0),getByType:e=>t.get(e)})});class ut{constructor(t,e=t.definition){"string"==typeof e&&(e={name:e}),this.type=t,this.name=e.name,this.template=e.template;const s=at.collect(t,e.attributes),i=new Array(s.length),n={},o={};for(let t=0,e=s.length;t<e;++t){const e=s[t];i[t]=e.attribute,n[e.name]=e,o[e.attribute]=e}this.attributes=s,this.observedAttributes=i,this.propertyLookup=n,this.attributeLookup=o,this.shadowOptions=void 0===e.shadowOptions?ct:null===e.shadowOptions?void 0:Object.assign(Object.assign({},ct),e.shadowOptions),this.elementOptions=void 0===e.elementOptions?ht:Object.assign(Object.assign({},ht),e.elementOptions),this.styles=void 0===e.styles?void 0:Array.isArray(e.styles)?X.create(e.styles):e.styles instanceof X?e.styles:X.create([e.styles])}get isDefined(){return!!dt.getByType(this.type)}define(t=customElements){const e=this.type;if(dt.register(this)){const t=this.attributes,s=e.prototype;for(let e=0,i=t.length;e<i;++e)g.defineProperty(s,t[e]);Reflect.defineProperty(e,"observedAttributes",{value:this.observedAttributes,enumerable:!0})}return t.get(this.name)||t.define(this.name,e,this.elementOptions),this}}ut.forType=dt.getByType;const ft=new WeakMap,bt={bubbles:!0,composed:!0,cancelable:!0};function pt(t){return t.shadowRoot||ft.get(t)||null}class mt extends m{constructor(t,e){super(t),this.boundObservables=null,this.behaviors=null,this.needsInitialization=!0,this._template=null,this._styles=null,this._isConnected=!1,this.$fastController=this,this.view=null,this.element=t,this.definition=e;const s=e.shadowOptions;if(void 0!==s){const e=t.attachShadow(s);"closed"===s.mode&&ft.set(t,e)}const i=g.getAccessors(t);if(i.length>0){const e=this.boundObservables=Object.create(null);for(let s=0,n=i.length;s<n;++s){const n=i[s].name,o=t[n];void 0!==o&&(delete t[n],e[n]=o)}}}get isConnected(){return g.track(this,"isConnected"),this._isConnected}setIsConnected(t){this._isConnected=t,g.notify(this,"isConnected")}get template(){return this._template}set template(t){this._template!==t&&(this._template=t,this.needsInitialization||this.renderTemplate(t))}get styles(){return this._styles}set styles(t){this._styles!==t&&(null!==this._styles&&this.removeStyles(this._styles),this._styles=t,this.needsInitialization||null===t||this.addStyles(t))}addStyles(t){const e=pt(this.element)||this.element.getRootNode();if(t instanceof HTMLStyleElement)e.append(t);else if(!t.isAttachedTo(e)){const s=t.behaviors;t.addStylesTo(e),null!==s&&this.addBehaviors(s)}}removeStyles(t){const e=pt(this.element)||this.element.getRootNode();if(t instanceof HTMLStyleElement)e.removeChild(t);else if(t.isAttachedTo(e)){const s=t.behaviors;t.removeStylesFrom(e),null!==s&&this.removeBehaviors(s)}}addBehaviors(t){const e=this.behaviors||(this.behaviors=new Map),s=t.length,i=[];for(let n=0;n<s;++n){const s=t[n];e.has(s)?e.set(s,e.get(s)+1):(e.set(s,1),i.push(s))}if(this._isConnected){const t=this.element;for(let e=0;e<i.length;++e)i[e].bind(t,w)}}removeBehaviors(t,e=!1){const s=this.behaviors;if(null===s)return;const i=t.length,n=[];for(let o=0;o<i;++o){const i=t[o];if(s.has(i)){const t=s.get(i)-1;0===t||e?s.delete(i)&&n.push(i):s.set(i,t)}}if(this._isConnected){const t=this.element;for(let e=0;e<n.length;++e)n[e].unbind(t)}}onConnectedCallback(){if(this._isConnected)return;const t=this.element;this.needsInitialization?this.finishInitialization():null!==this.view&&this.view.bind(t,w);const e=this.behaviors;if(null!==e)for(const[s]of e)s.bind(t,w);this.setIsConnected(!0)}onDisconnectedCallback(){if(!this._isConnected)return;this.setIsConnected(!1);const t=this.view;null!==t&&t.unbind();const e=this.behaviors;if(null!==e){const t=this.element;for(const[s]of e)s.unbind(t)}}onAttributeChangedCallback(t,e,s){const i=this.definition.attributeLookup[t];void 0!==i&&i.onAttributeChangedCallback(this.element,s)}emit(t,e,s){return!!this._isConnected&&this.element.dispatchEvent(new CustomEvent(t,Object.assign(Object.assign({detail:e},bt),s)))}finishInitialization(){const t=this.element,e=this.boundObservables;if(null!==e){const s=Object.keys(e);for(let i=0,n=s.length;i<n;++i){const n=s[i];t[n]=e[n]}this.boundObservables=null}const s=this.definition;null===this._template&&(this.element.resolveTemplate?this._template=this.element.resolveTemplate():s.template&&(this._template=s.template||null)),null!==this._template&&this.renderTemplate(this._template),null===this._styles&&(this.element.resolveStyles?this._styles=this.element.resolveStyles():s.styles&&(this._styles=s.styles||null)),null!==this._styles&&this.addStyles(this._styles),this.needsInitialization=!1}renderTemplate(t){const e=this.element,s=pt(e)||e;null!==this.view?(this.view.dispose(),this.view=null):this.needsInitialization||b.removeChildNodes(s),t&&(this.view=t.render(e,s,e))}static forCustomElement(t){const e=t.$fastController;if(void 0!==e)return e;const s=ut.forType(t.constructor);if(void 0===s)throw new Error("Missing FASTElement definition.");return t.$fastController=new mt(t,s)}}function gt(t){return class extends t{constructor(){super(),mt.forCustomElement(this)}$emit(t,e,s){return this.$fastController.emit(t,e,s)}connectedCallback(){this.$fastController.onConnectedCallback()}disconnectedCallback(){this.$fastController.onDisconnectedCallback()}attributeChangedCallback(t,e,s){this.$fastController.onAttributeChangedCallback(t,e,s)}}}const vt=Object.assign(gt(HTMLElement),{from:t=>gt(t),define:(t,e)=>new ut(t,e).define().type});var yt=s(7657);class St{createCSS(){return""}createBehavior(){}}const wt=(function(t,...e){const{styles:s,behaviors:i}=function(t,e){const s=[];let i="";const n=[];for(let o=0,r=t.length-1;o<r;++o){i+=t[o];let r=e[o];if(r instanceof St){const t=r.createBehavior();r=r.createCSS(),t&&n.push(t)}r instanceof X||r instanceof CSSStyleSheet?(""!==i.trim()&&(s.push(i),i=""),s.push(r)):i+=r}return i+=t[t.length-1],""!==i.trim()&&s.push(i),{styles:s,behaviors:n}}(t,e),n=X.create(s);return i.length&&n.withBehaviors(...i),n})`
	.modal-background {
		bottom: 0;
		left: 0;
		position: fixed;
		right: 0;
		top: 0;
		z-index: 1040;
	}
	.modal-background + div:not(.modal-content) {
		width: auto;
		height: auto;
	}
	.modal-card {
		top: 30%;
		max-width: 650px;
		z-index: 10001;
		margin: 0 auto;
		overflow: visible;
	}
`;class Ct extends vt{constructor(){super(...arguments),this.visible=!1,this.locStrings=yt.p,this.update=!0}connectedCallback(){super.connectedCallback(),this.JSONLocStrings&&this.update&&this.setLocStrings()}setLocStrings(){this.update=!1;try{this.locStrings=JSON.parse(this.JSONLocStrings)}catch(t){this.locStrings=yt.p}}confirm(){this.visible=!1,this.$emit("confirm"),this.showVerticalScrollbar()}cancel(){this.visible=!1,this.$emit("cancel"),this.showVerticalScrollbar()}close(){this.visible=!1,this.$emit("close"),this.showVerticalScrollbar()}setFocus(){b.queueUpdate(()=>{const t=document.getElementsByClassName("default-focus")[0];t&&t.focus();const e=document.querySelector(".modal-card").querySelectorAll(".modal-close, .modal-card .button"),s=e[0],i=e[e.length-1];document.addEventListener("keydown",t=>{("Tab"===t.key||9===t.keyCode)&&(t.shiftKey?document.activeElement===s&&(i.focus(),t.preventDefault()):document.activeElement===i&&(s.focus(),t.preventDefault()))})})}hideVerticalScrollbar(){document.getElementsByTagName("html")[0].style.overflowY="hidden"}showVerticalScrollbar(){document.getElementsByTagName("html")[0].removeAttribute("style")}}i([v],Ct.prototype,"visible",void 0),i([v],Ct.prototype,"closeString",void 0),i([function(t,e){let s;function i(t,e){arguments.length>1&&(s.property=e),rt.locate(t.constructor).push(s)}return arguments.length>1?(s={},void i(t,e)):(s=void 0===t?{}:t,i)}],Ct.prototype,"JSONLocStrings",void 0),i([v],Ct.prototype,"locStrings",void 0);var xt=s(6930);const Tt="popover-modal",kt=Q`
	${G(t=>t.visible,Q`<div class="modal-background">
			<div class="modal-card">
				<header class="modal-card-head padding-xxs">
					<button
						class="modal-close modal-card-close-button is-large"
						aria-pressed="false"
						aria-label="${t=>t.locStrings.loc_close}"
						@click="${t=>t.closeModal()}"
					></button>
				</header>
				<section class="modal-card-body padding-top-none">
					${G(t=>!t.errorVisible,t=>{return e=t.locStrings.loc_admin_markdownEditor_codeBlockLanguagePlaceholder,s=t.locStrings.loc_admin_markdownEditor_save,i=t=>t.confirm(),Q`
		<h3 id="popover-modal-heading" class="title">${e}</h3>
		<form class="d-flex fd-column" @onsubmit="${(t,e)=>e.event.preventDefault()}">
			<div class="d-flex gs4 gsy fd-column code-block-form">
				<span id="code-block-autocomplete"></span>
			</div>
			<aside
				class="s-notice s-notice__warning d-none m8 js-validation-message"
				role="status"
				aria-hidden="true"
			></aside>
			<button
				class="button button-primary margin-top-xs"
				aria-pressed="false"
				@click="${(t,e)=>{e.event.preventDefault(),i(t)}}"
			>
				${s}
			</button>
		</form>
	`;var e,s,i})}
					${G(t=>t.errorVisible,Q`
						<h3 id="popover-modal-heading" class="title">${t=>t.locStrings.loc_error}</h3>
						<p>${t=>t.customMessage}</p>
						<div class="buttons buttons-right padding-top-xs">
							<button
							type="button" class="default-focus button font-weight-semibold modal-close button-primary button-filled" @click="${t=>t.closeModal()}">
								<span>${t=>t.locStrings.loc_ok}<span>
							</button>
						</div>
						`)}
				</section>
			</div>
		</div>`)}
`;let Ot=class extends Ct{constructor(){super(...arguments),this.customMessage="",this.errorVisible=!1,this.clickHandler=t=>{const e=t.target;(e.closest(".modal-close")||e.classList.contains("modal-background"))&&(t.preventDefault(),this.closeModal())},this.escHandler=t=>{27===t.keyCode&&(t.preventDefault(),this.closeModal())},this.restoreScrollbar=()=>{}}showModal(t){this.visible=!0,this.callback=t,this.setAttribute("tabindex","-1"),this.classList.add("modal","has-default-focus"),this.wrapper=document.createElement("div"),this.wrapper.setAttribute("data-bi-name","modal"),this.wrapper.insertAdjacentElement("afterbegin",this),document.body.insertAdjacentElement("afterbegin",(0,xt.iE)(document)),document.body.insertAdjacentElement("afterbegin",this.wrapper),this.addEventListener("click",this.clickHandler),this.addEventListener("keydown",this.escHandler),this.restoreScrollbar=function(t=document.documentElement,e=document.documentElement||document.body,s=(document.documentElement||document.body).scrollTop){return e.style.left="0",e.style.right="0",e.style.top=`-${s}px`,e.style.position="fixed",(i=!0)=>{e.style.left="",e.style.right="",e.style.top="",e.style.position="",i&&(t.scrollTop=s)}}(document.documentElement,document.scrollingElement||document.documentElement,(document.scrollingElement||document.documentElement||document.body).scrollTop),this.classList.add("is-active"),document.body.insertAdjacentElement("afterbegin",(0,xt.iE)(document)),this.lastFocus=document.activeElement,this.focusHandler=(0,xt.SD)(this.wrapper),this.setFocus(),(0,xt.ge)(this),super.hideVerticalScrollbar()}confirm(){this.visible=!1,super.showVerticalScrollbar(),this.callback(),this.closeModal()}showError(t){this.visible=!0,this.errorVisible=!0,this.customMessage=t,this.setFocus()}closeModal(){if(this.visible=!1,this.errorVisible=!1,super.showVerticalScrollbar(),this.restoreScrollbar(),this.classList.remove("is-active"),document.body.insertAdjacentElement("afterbegin",this),!this.wrapper)return this.remove();this.wrapper.parentElement?.removeChild(this.wrapper),document.body.querySelectorAll(".modal-tab-sentinel").forEach(t=>document.body.removeChild(t)),document.body.querySelectorAll(`${Tt}.modal.is-active`).forEach(t=>t.remove()),window.removeEventListener("focus",this.focusHandler),this.wrapper.removeEventListener("click",this.clickHandler),this.wrapper.removeEventListener("keydown",this.escHandler),this.lastFocus&&this.lastFocus instanceof HTMLElement&&this.lastFocus.focus()}};var Bt;i([v],Ot.prototype,"customMessage",void 0),i([v],Ot.prototype,"errorVisible",void 0),i([v],Ot.prototype,"callback",void 0),i([v],Ot.prototype,"wrapper",void 0),i([v],Ot.prototype,"lastFocus",void 0),i([v],Ot.prototype,"focusHandler",void 0),Ot=i([(Bt={name:Tt,styles:wt,template:kt,shadowOptions:null},function(t){new ut(t,Bt).define()})],Ot)}}]);
// SIG // Begin signature block
// SIG // MIIovQYJKoZIhvcNAQcCoIIorjCCKKoCAQExDzANBglg
// SIG // hkgBZQMEAgEFADB3BgorBgEEAYI3AgEEoGkwZzAyBgor
// SIG // BgEEAYI3AgEeMCQCAQEEEBDgyQbOONQRoqMAEEvTUJAC
// SIG // AQACAQACAQACAQACAQAwMTANBglghkgBZQMEAgEFAAQg
// SIG // llXMa5GpqnSGlegdETwkDwij5RGsoIl/d97IEm1AXaeg
// SIG // gg3DMIIGrTCCBJWgAwIBAgITMwAAANMCiNhpvd8CCQAA
// SIG // AAAA0zANBgkqhkiG9w0BAQwFADBiMQswCQYDVQQGEwJV
// SIG // UzEeMBwGA1UEChMVTWljcm9zb2Z0IENvcnBvcmF0aW9u
// SIG // MTMwMQYDVQQDEypBenVyZSBSU0EgUHVibGljIFNlcnZp
// SIG // Y2VzIENvZGUgU2lnbmluZyBQQ0EwHhcNMjYwMzA1MTkw
// SIG // NjE5WhcNMjcwMzAzMTkwNjE5WjCBgjELMAkGA1UEBhMC
// SIG // VVMxEzARBgNVBAgTCldhc2hpbmd0b24xEDAOBgNVBAcT
// SIG // B1JlZG1vbmQxHjAcBgNVBAoTFU1pY3Jvc29mdCBDb3Jw
// SIG // b3JhdGlvbjEsMCoGA1UEAxMjQXp1cmUgUHVibGljIFNl
// SIG // cnZpY2VzIFJTQSBDb2RlIFNpZ24wggGiMA0GCSqGSIb3
// SIG // DQEBAQUAA4IBjwAwggGKAoIBgQDJrDsZxGHNBYj5RPkR
// SIG // yGEIGZlcCQkqE7SdGa6c2FPAMGu1JLqHur8qNWjR5swe
// SIG // kMMn0WSz2+QE0c848wHvqVVLpWV+Un3Q01Dnyzjifae4
// SIG // h+kzhQTUIhX2rKQbGHdqBe7LXyCgkfDrTNLXsI1xAXAw
// SIG // A42Ar+PpVd1ktqLSsM6pwqrM/FFfEizl9h5gtrEIZODp
// SIG // +jo9vESxKvHGp/Ifca7e/IluDeJffP4ME/fFtUzUCLH/
// SIG // IweugiUcsaTmewSny4odYLtmZK/zpBuPjGTLpUnn4HMy
// SIG // WXLUSOFlgvFrLKCPZxbNxXxBo5EUquzrFbpg9NmQVipJ
// SIG // QsKDSKNHluTwNicItFpZpiPMc7Y2LG11dNAil3yJEBLF
// SIG // MQ/5RqQptcWmgSKoG8Tx7x+RCYQj4Sjl2yJt+4OykVn9
// SIG // /kQ5wo6v6TmIHHZsKdmgIkMCKBuIRcB2FaGwLY+UGMP1
// SIG // xmiwIaekgjUgVwXX8Kv/2SYI9XXrjyUME4NLj0JTBIO7
// SIG // YX201gYYOL8CAwEAAaOCAbkwggG1MA4GA1UdDwEB/wQE
// SIG // AwIHgDAfBgNVHSUEGDAWBggrBgEFBQcDAwYKKwYBBAGC
// SIG // N1sBATAdBgNVHQ4EFgQU6DIfaqBAAm33/QFJGYifZUeQ
// SIG // B3AwRQYDVR0RBD4wPKQ6MDgxHjAcBgNVBAsTFU1pY3Jv
// SIG // c29mdCBDb3Jwb3JhdGlvbjEWMBQGA1UEBRMNNDY5OTgx
// SIG // KzUwNzE4MTAfBgNVHSMEGDAWgBTxL7qRFnzefVInMfV6
// SIG // +9VYWWk6PTBvBgNVHR8EaDBmMGSgYqBghl5odHRwOi8v
// SIG // d3d3Lm1pY3Jvc29mdC5jb20vcGtpb3BzL2NybC9BenVy
// SIG // ZSUyMFJTQSUyMFB1YmxpYyUyMFNlcnZpY2VzJTIwQ29k
// SIG // ZSUyMFNpZ25pbmclMjBQQ0EuY3JsMHwGCCsGAQUFBwEB
// SIG // BHAwbjBsBggrBgEFBQcwAoZgaHR0cDovL3d3dy5taWNy
// SIG // b3NvZnQuY29tL3BraW9wcy9jZXJ0cy9BenVyZSUyMFJT
// SIG // QSUyMFB1YmxpYyUyMFNlcnZpY2VzJTIwQ29kZSUyMFNp
// SIG // Z25pbmclMjBQQ0EuY3J0MAwGA1UdEwEB/wQCMAAwDQYJ
// SIG // KoZIhvcNAQEMBQADggIBAKJEWoxuo4PDUOPrpeqZZBdc
// SIG // EBjIoYQZjSvEIMTd0fcf89rWN/fr6cbAs3fZtR1LQ2kR
// SIG // Wo2mYixmAQpm6ijAYu3Qg+/NIHofviOVCDqHmaQGEiwi
// SIG // oBsb7Et9V7B9rqsksJslTyCJUJYuIXaKv37suPC7cFpX
// SIG // aaWaNLn0juz1sPKdklvTO23fwcahgRO9nqd9gTi9j6dw
// SIG // /nEJURWo32dl+rxdylnuRd6RHpkJKdlPVXRrr/ZL8sby
// SIG // akoCUN4zNVivUMLmUspYRJIV2TpkZonQnrmTm6TpXGVg
// SIG // Cjj56duTzVa/GRAKLVBHNm8je6esjgoswv6eHmYkmgJR
// SIG // jvZ+eHNloLnXfqByg3CxJ0Gd+nja5RTavYplIc9zfOgq
// SIG // Ng5e6NW8E0Q/AI115WfpM+ncWenWqdPs1YLinyUdRDxi
// SIG // DTmhYTyN1p3FojGtyM+mrQVIvC2l8zQr/LNCTvz/dj2h
// SIG // WqsF/7SDnK4wE812YAp6pPfgtr6BfVD0LMJu+s6f2PXe
// SIG // oLskA4Ac2PoJz5N7FmeY7Wn5shZBf4hOqCJssd5ZBpUb
// SIG // tGYh3iCnQSJP9EokoxVxe7D5HmkqTRNnXqIDQ5zW6bL3
// SIG // SDCYFEG5EWtqV9Ytd0Mjplx/s5+w1TnYbXIKbPzi4Hnb
// SIG // 3Xr0m8YnMuVyhmxGyHZ2CjMpQclgocs2QNsOyr7evLGD
// SIG // MIIHDjCCBPagAwIBAgITMwAAAAKyxJOIeFns0wAAAAAA
// SIG // AjANBgkqhkiG9w0BAQwFADBbMQswCQYDVQQGEwJVUzEe
// SIG // MBwGA1UEChMVTWljcm9zb2Z0IENvcnBvcmF0aW9uMSww
// SIG // KgYDVQQDEyNNaWNyb3NvZnQgUlNBIFNlcnZpY2VzIFJv
// SIG // b3QgQ0EgMjAyMTAeFw0yMTA5MDIxNzQxMTlaFw0zNjA5
// SIG // MDIxNzUxMTlaMGIxCzAJBgNVBAYTAlVTMR4wHAYDVQQK
// SIG // ExVNaWNyb3NvZnQgQ29ycG9yYXRpb24xMzAxBgNVBAMT
// SIG // KkF6dXJlIFJTQSBQdWJsaWMgU2VydmljZXMgQ29kZSBT
// SIG // aWduaW5nIFBDQTCCAiIwDQYJKoZIhvcNAQEBBQADggIP
// SIG // ADCCAgoCggIBAKXd/Sy91nFgseVJOFgeRhVxrcahyp1Y
// SIG // GSN0FpOEgEREVb3ND/QgI7I0yd7XG6OE8Vomr5FMxvK8
// SIG // TvJ4Lc6LP9BDz2GSa1M0LlzHKX757/24C0ZndzccA1qQ
// SIG // i00+BmmOr4plmxRzTFv4Phdw8yBPF9GDvClqV8ASvvbi
// SIG // tfjaD7dVPOFLb7N7fvt/qWogGN5eis0FXCqVJdmPZZaX
// SIG // 2h4iG0otsAhfq8yvSlJ0YwO4i5GDeLQwTsMN1Rf2UAHQ
// SIG // KCUYkFsLSQ0mqbaRbDZhB+2pFL/q/c2a6hlHLnapYyfw
// SIG // lNFXkDhwAFWEzfwFHER2oR42UayfN9tsO/p2tWk33Crn
// SIG // HdndJDrIZ6oQ3D+Ngol/TR8BAgXCIM6se6YlLDTsxRwh
// SIG // 9QUDq7KVhKy58HGKJUqwgIW0E7cvlzUl0Hft/ebhALZy
// SIG // FDkhof9C5Cq4c/486XLjQq0nbuKsFNhQU0yvABR3eohw
// SIG // 63Kps66Uma48oE0JmqOxmzrPvrITYcsnByKleiHn+4yq
// SIG // +Ts/KrtqkQwQcuikMPrZwXCtsYkxMUyUn8gr8oew22WD
// SIG // eIQECAM1Cz9TcdJadsrToKqXQa2bAn/AABAYyogPPONf
// SIG // GvojTI3DlYD42etMa/gPeZJavX+z7x8d/4eYBnJ9WFSi
// SIG // 9q0v+vLOGc3fyM2KQtq5eVbHX5rVyWc6bJ35AgMBAAGj
// SIG // ggHCMIIBvjAQBgkrBgEEAYI3FQEEAwIBADAdBgNVHQ4E
// SIG // FgQU8S+6kRZ83n1SJzH1evvVWFlpOj0wVAYDVR0gBE0w
// SIG // SzBJBgRVHSAAMEEwPwYIKwYBBQUHAgEWM2h0dHA6Ly93
// SIG // d3cubWljcm9zb2Z0LmNvbS9wa2lvcHMvRG9jcy9SZXBv
// SIG // c2l0b3J5Lmh0bTAZBgkrBgEEAYI3FAIEDB4KAFMAdQBi
// SIG // AEMAQTALBgNVHQ8EBAMCAYYwDwYDVR0TAQH/BAUwAwEB
// SIG // /zAfBgNVHSMEGDAWgBQODLFkab0tsdVrJqZH6lZOgMPt
// SIG // ijBmBgNVHR8EXzBdMFugWaBXhlVodHRwOi8vd3d3Lm1p
// SIG // Y3Jvc29mdC5jb20vcGtpb3BzL2NybC9NaWNyb3NvZnQl
// SIG // MjBSU0ElMjBTZXJ2aWNlcyUyMFJvb3QlMjBDQSUyMDIw
// SIG // MjEuY3JsMHMGCCsGAQUFBwEBBGcwZTBjBggrBgEFBQcw
// SIG // AoZXaHR0cDovL3d3dy5taWNyb3NvZnQuY29tL3BraW9w
// SIG // cy9jZXJ0cy9NaWNyb3NvZnQlMjBSU0ElMjBTZXJ2aWNl
// SIG // cyUyMFJvb3QlMjBDQSUyMDIwMjEuY3J0MA0GCSqGSIb3
// SIG // DQEBDAUAA4ICAQBin7PMBnXjnIJ0x++LnudLDWWnZ8dZ
// SIG // mJ14DuZfUss/doUThLAM4crrHaTbJoulUUELNd2AnOpX
// SIG // /Z4tenUMT3sjYIdPYyJfIYWPRqfI6Nbz+JVK7RRvn2nl
// SIG // 5EEMIuRE6UKS9ZGBbf02a7sb04E/7BN/NhhrmtS/tVFj
// SIG // fRrrVh9zXku45rqWuCwUTzg3EqxKQ8OGbtjBQtq/Syb/
// SIG // clm5BHsoh3XhMnb9VLv3G1duNf90FL5/o88XZ4L18nx1
// SIG // lfky2nllY4HIA8PK8AarqAW4iKSTA3EGqn8s/47WtQKT
// SIG // +qED2YbZXVOYL+L7vQDCnFbwhgAx6ucuMz7Ae1rqibg3
// SIG // AjsC7U5M3oA/vqAHDKDA3mdM5D6L/ZEdQgaG20HhUOSQ
// SIG // +CiQD3TyHSiVCfVMuTv83IiKCni3LW/23tHC2tbN57rl
// SIG // hMcoyjIi+IVd7j7s41MFBaDwJrmfXn/YM+lR/5QqvO7z
// SIG // WAbbr/XU531v3jr/jBilmrqt6U/b7y8TXyA9nYxV9iSM
// SIG // FmcbyIi2xgdcAHhxnpXcvcvyFWET6YiJiyeSJZwwJv8g
// SIG // wXiBF+Zh0IHArl6KVsbAdsATuP1TCEBpPynXZmkviIEW
// SIG // Ptnv315ZjTC7nPoOpSnOVaO7wZztrOefZunI5fBxw7mG
// SIG // 1oyoRnADZawiFsVo9J/cDu15ErRCfDQRhwSiBTGCGlIw
// SIG // ghpOAgEBMHkwYjELMAkGA1UEBhMCVVMxHjAcBgNVBAoT
// SIG // FU1pY3Jvc29mdCBDb3Jwb3JhdGlvbjEzMDEGA1UEAxMq
// SIG // QXp1cmUgUlNBIFB1YmxpYyBTZXJ2aWNlcyBDb2RlIFNp
// SIG // Z25pbmcgUENBAhMzAAAA0wKI2Gm93wIJAAAAAADTMA0G
// SIG // CWCGSAFlAwQCAQUAoIGQMBkGCSqGSIb3DQEJAzEMBgor
// SIG // BgEEAYI3AgEEMC8GCSqGSIb3DQEJBDEiBCAR5jtMWzMP
// SIG // 1sCgJbahxcJPYpJfQcSp/124TeGej/a7szBCBgorBgEE
// SIG // AYI3AgEMMTQwMqAUgBIATQBpAGMAcgBvAHMAbwBmAHSh
// SIG // GoAYaHR0cDovL3d3dy5taWNyb3NvZnQuY29tMA0GCSqG
// SIG // SIb3DQEBAQUABIIBgAKTXwu0mxK7plzMJcePcEnfvtwM
// SIG // bD69VjSsYR0HsYJ1MSnTVsOIskqtM+e0nU29gQjChxOu
// SIG // w/eDrERO19iRmo1GYN/qCcXywk9wbNNI5hV+kPjMEFdY
// SIG // jNTj3Gf65ZLUSxosfe9jdaAh6VcHl7Cpqk6IISGzxk5q
// SIG // PuXP4szxDEfqiWCzBaqkDQLPFYfCQZSvMxqnFR1wDwij
// SIG // DlM1+UA6ELKF4GWfzhQu/Q/LBkKFrT9/XK8Z2bajf5RM
// SIG // AxHuVhATF0kQ7Vz818wNWUfpPEVjJIexqbtQvGhEdm/Z
// SIG // 4QyDi32Wj6zFMpfq4NsTapfumHOt9CMZ+R6aiTpGCz+3
// SIG // l3BUeS/Z+ENgxLt01QN6aL6+rkPgqgPDT2DeboX2Dg0E
// SIG // zBcA7+pIOVcAj8GtyntumW6nKAGb9ODiSnJKJIIHqmPi
// SIG // v587fitukB2ZeIDlnbeSWWFZm7JaUCQvSQxJt/P5eZDF
// SIG // YvDoArt+Ueyf+RinUfw7zqjIPU4Fo+yaK5m05VAxDsdM
// SIG // haGCF5cwgheTBgorBgEEAYI3AwMBMYIXgzCCF38GCSqG
// SIG // SIb3DQEHAqCCF3AwghdsAgEDMQ8wDQYJYIZIAWUDBAIB
// SIG // BQAwggFSBgsqhkiG9w0BCRABBKCCAUEEggE9MIIBOQIB
// SIG // AQYKKwYBBAGEWQoDATAxMA0GCWCGSAFlAwQCAQUABCCr
// SIG // SO5dKx7EZtXtMymyU8M3U5SY8Tt1o6+6Rx4haEfYHAIG
// SIG // al/63Q/DGBMyMDI2MDgwNjAyMTgxMi44NzZaMASAAgH0
// SIG // oIHRpIHOMIHLMQswCQYDVQQGEwJVUzETMBEGA1UECBMK
// SIG // V2FzaGluZ3RvbjEQMA4GA1UEBxMHUmVkbW9uZDEeMBwG
// SIG // A1UEChMVTWljcm9zb2Z0IENvcnBvcmF0aW9uMSUwIwYD
// SIG // VQQLExxNaWNyb3NvZnQgQW1lcmljYSBPcGVyYXRpb25z
// SIG // MScwJQYDVQQLEx5uU2hpZWxkIFRTUyBFU046N0YwMC0w
// SIG // NUUwLUQ5NDcxJTAjBgNVBAMTHE1pY3Jvc29mdCBUaW1l
// SIG // LVN0YW1wIFNlcnZpY2WgghHtMIIHIDCCBQigAwIBAgIT
// SIG // MwAAAh6jrKRuOW98SQABAAACHjANBgkqhkiG9w0BAQsF
// SIG // ADB8MQswCQYDVQQGEwJVUzETMBEGA1UECBMKV2FzaGlu
// SIG // Z3RvbjEQMA4GA1UEBxMHUmVkbW9uZDEeMBwGA1UEChMV
// SIG // TWljcm9zb2Z0IENvcnBvcmF0aW9uMSYwJAYDVQQDEx1N
// SIG // aWNyb3NvZnQgVGltZS1TdGFtcCBQQ0EgMjAxMDAeFw0y
// SIG // NjAyMTkxOTM5NDlaFw0yNzA1MTcxOTM5NDlaMIHLMQsw
// SIG // CQYDVQQGEwJVUzETMBEGA1UECBMKV2FzaGluZ3RvbjEQ
// SIG // MA4GA1UEBxMHUmVkbW9uZDEeMBwGA1UEChMVTWljcm9z
// SIG // b2Z0IENvcnBvcmF0aW9uMSUwIwYDVQQLExxNaWNyb3Nv
// SIG // ZnQgQW1lcmljYSBPcGVyYXRpb25zMScwJQYDVQQLEx5u
// SIG // U2hpZWxkIFRTUyBFU046N0YwMC0wNUUwLUQ5NDcxJTAj
// SIG // BgNVBAMTHE1pY3Jvc29mdCBUaW1lLVN0YW1wIFNlcnZp
// SIG // Y2UwggIiMA0GCSqGSIb3DQEBAQUAA4ICDwAwggIKAoIC
// SIG // AQCl0TjtbDwsR7Fe8ac6ol5s1zhtTqd2AWpchQhLp9G5
// SIG // mmSM23N5fyQGCQ1D06rOA3PgXKF+76vXvOCs2VsLv1ow
// SIG // j4mHEyEqiq8GJ5yC+/QNYRpZPA8e7OgekzDO6S/4vy/j
// SIG // TMYbp3rhuFiKKCzTWOQtdFcF+D0k369I7pm/E07SyNMG
// SIG // kuNd5lj5SJ91UqFuZfjMB6cQ2wh77mtiRUVdj53yjdNq
// SIG // j+GQl+Yaz29Bjrzn7U1ln+JpLlnb0xdGmZoIPKZbwBVc
// SIG // WtyL4uyhML7SSTmiOfWXU+g+yNl0CdoLGL8LtWHEi8Fs
// SIG // uTPeSdSqmeMrvLaEmibTVTS4vQQY8NPnb6uI5y6iNV9v
// SIG // BFcm8LU/lDTjGTqPa7UBT4gdf5Jm3wYrfCFZ4P/j5Moq
// SIG // T0JONca50jt4TGI90SihXaDEYqk23S0IJZ3UkUpukDRT
// SIG // jK713BIykffxyBqMeQqfO0zvWfUx7BrmUpugQcw99+Dx
// SIG // Ll2gf+uQEpRmnlbrVJ9dvW9ds4fqEPN2jG0QwF1PBSgl
// SIG // NcV1SpqZKitQgBGSwu/82AKztoCHwYRHRNwzwTVe/1KN
// SIG // TvmqAd4Uges4ywOH02haagT8wYY8OdWdjKn3k052w+km
// SIG // c0UC0F+iVXTGZIMxvo9iBZQoXehzRtWJ/VOtKvCyS3cs
// SIG // KzN7rStWJwjSWz6dtOf0l+ytLQIDAQABo4IBSTCCAUUw
// SIG // HQYDVR0OBBYEFOYKFprqBB0JZmJcFC4cPPmeF4JkMB8G
// SIG // A1UdIwQYMBaAFJ+nFV0AXmJdg/Tl0mWnG1M1GelyMF8G
// SIG // A1UdHwRYMFYwVKBSoFCGTmh0dHA6Ly93d3cubWljcm9z
// SIG // b2Z0LmNvbS9wa2lvcHMvY3JsL01pY3Jvc29mdCUyMFRp
// SIG // bWUtU3RhbXAlMjBQQ0ElMjAyMDEwKDEpLmNybDBsBggr
// SIG // BgEFBQcBAQRgMF4wXAYIKwYBBQUHMAKGUGh0dHA6Ly93
// SIG // d3cubWljcm9zb2Z0LmNvbS9wa2lvcHMvY2VydHMvTWlj
// SIG // cm9zb2Z0JTIwVGltZS1TdGFtcCUyMFBDQSUyMDIwMTAo
// SIG // MSkuY3J0MAwGA1UdEwEB/wQCMAAwFgYDVR0lAQH/BAww
// SIG // CgYIKwYBBQUHAwgwDgYDVR0PAQH/BAQDAgeAMA0GCSqG
// SIG // SIb3DQEBCwUAA4ICAQCkoZB5NnJVFb5wKejRonk518a2
// SIG // TBNYpKcBMtfL6BS0ARaABOMGYLlPNuhI1HwmelP9hX3o
// SIG // q3TaEm/cDkkzNQAzDedPgoRI2R7+8poNSWvHXEAs7SZO
// SIG // Dm9x7KqlBkNZM9ex4XY1yNmVOAmWDjRr7jKjaiQbntf7
// SIG // EC4GNikxGGaVWOjfYt3Q9X0r/Ks8KBlbzDR9zjA/TCct
// SIG // R4co1WpU1ZRLFrB9bl8dRxsbnyT2qQ41E7dT12R30eIG
// SIG // UziEs5GN+26V/ovXOi20dJiM13hYWvy1NNJAhkKOlLB1
// SIG // ONund6ffhPdUcHWsu8V+lR0aakMV64HqDbLumZrCNwUo
// SIG // fVx3xMk8F4tCYJtQxLTywc30sZAD1S2sC1959x6KixA+
// SIG // p41FLUl8g64oHy3bfYnH5xd4JOBgQoaqndGjcctxr+8E
// SIG // knjhKyrgAzrTcKLJbUezgoye8brCLJ+y6PAoEjpXRkSY
// SIG // AU8wfQ3YWRck6ALwoV7Uin8+rpGQSbXhF6c1dTFakXmC
// SIG // hClud4IADY/t6JRkJ+06FzL+jDd8KLV8Qj77JfiuTiPI
// SIG // G5G/xlnGoZFcX+yyBtDvzZE48d+Y+HYUd/cvhH1FKl7A
// SIG // H+5AyotqJSFmvM/BuYRx2B20asVXilV2k2JbNO3LGCz3
// SIG // Q+dpElzwsfJrka1N/getma7fWpowsNvoIaEQvjad8TCC
// SIG // B3EwggVZoAMCAQICEzMAAAAVxedrngKbSZkAAAAAABUw
// SIG // DQYJKoZIhvcNAQELBQAwgYgxCzAJBgNVBAYTAlVTMRMw
// SIG // EQYDVQQIEwpXYXNoaW5ndG9uMRAwDgYDVQQHEwdSZWRt
// SIG // b25kMR4wHAYDVQQKExVNaWNyb3NvZnQgQ29ycG9yYXRp
// SIG // b24xMjAwBgNVBAMTKU1pY3Jvc29mdCBSb290IENlcnRp
// SIG // ZmljYXRlIEF1dGhvcml0eSAyMDEwMB4XDTIxMDkzMDE4
// SIG // MjIyNVoXDTMwMDkzMDE4MzIyNVowfDELMAkGA1UEBhMC
// SIG // VVMxEzARBgNVBAgTCldhc2hpbmd0b24xEDAOBgNVBAcT
// SIG // B1JlZG1vbmQxHjAcBgNVBAoTFU1pY3Jvc29mdCBDb3Jw
// SIG // b3JhdGlvbjEmMCQGA1UEAxMdTWljcm9zb2Z0IFRpbWUt
// SIG // U3RhbXAgUENBIDIwMTAwggIiMA0GCSqGSIb3DQEBAQUA
// SIG // A4ICDwAwggIKAoICAQDk4aZM57RyIQt5osvXJHm9DtWC
// SIG // 0/3unAcH0qlsTnXIyjVX9gF/bErg4r25PhdgM/9cT8dm
// SIG // 95VTcVrifkpa/rg2Z4VGIwy1jRPPdzLAEBjoYH1qUoNE
// SIG // t6aORmsHFPPFdvWGUNzBRMhxXFExN6AKOG6N7dcP2CZT
// SIG // fDlhAnrEqv1yaa8dq6z2Nr41JmTamDu6GnszrYBbfowQ
// SIG // HJ1S/rboYiXcag/PXfT+jlPP1uyFVk3v3byNpOORj7I5
// SIG // LFGc6XBpDco2LXCOMcg1KL3jtIckw+DJj361VI/c+gVV
// SIG // mG1oO5pGve2krnopN6zL64NF50ZuyjLVwIYwXE8s4mKy
// SIG // zbnijYjklqwBSru+cakXW2dg3viSkR4dPf0gz3N9QZpG
// SIG // dc3EXzTdEonW/aUgfX782Z5F37ZyL9t9X4C626p+Nuw2
// SIG // TPYrbqgSUei/BQOj0XOmTTd0lBw0gg/wEPK3Rxjtp+iZ
// SIG // fD9M269ewvPV2HM9Q07BMzlMjgK8QmguEOqEUUbi0b1q
// SIG // GFphAXPKZ6Je1yh2AuIzGHLXpyDwwvoSCtdjbwzJNmSL
// SIG // W6CmgyFdXzB0kZSU2LlQ+QuJYfM2BjUYhEfb3BvR/bLU
// SIG // HMVr9lxSUV0S2yW6r1AFemzFER1y7435UsSFF5PAPBXb
// SIG // GjfHCBUYP3irRbb1Hode2o+eFnJpxq57t7c+auIurQID
// SIG // AQABo4IB3TCCAdkwEgYJKwYBBAGCNxUBBAUCAwEAATAj
// SIG // BgkrBgEEAYI3FQIEFgQUKqdS/mTEmr6CkTxGNSnPEP8v
// SIG // BO4wHQYDVR0OBBYEFJ+nFV0AXmJdg/Tl0mWnG1M1Gely
// SIG // MFwGA1UdIARVMFMwUQYMKwYBBAGCN0yDfQEBMEEwPwYI
// SIG // KwYBBQUHAgEWM2h0dHA6Ly93d3cubWljcm9zb2Z0LmNv
// SIG // bS9wa2lvcHMvRG9jcy9SZXBvc2l0b3J5Lmh0bTATBgNV
// SIG // HSUEDDAKBggrBgEFBQcDCDAZBgkrBgEEAYI3FAIEDB4K
// SIG // AFMAdQBiAEMAQTALBgNVHQ8EBAMCAYYwDwYDVR0TAQH/
// SIG // BAUwAwEB/zAfBgNVHSMEGDAWgBTV9lbLj+iiXGJo0T2U
// SIG // kFvXzpoYxDBWBgNVHR8ETzBNMEugSaBHhkVodHRwOi8v
// SIG // Y3JsLm1pY3Jvc29mdC5jb20vcGtpL2NybC9wcm9kdWN0
// SIG // cy9NaWNSb29DZXJBdXRfMjAxMC0wNi0yMy5jcmwwWgYI
// SIG // KwYBBQUHAQEETjBMMEoGCCsGAQUFBzAChj5odHRwOi8v
// SIG // d3d3Lm1pY3Jvc29mdC5jb20vcGtpL2NlcnRzL01pY1Jv
// SIG // b0NlckF1dF8yMDEwLTA2LTIzLmNydDANBgkqhkiG9w0B
// SIG // AQsFAAOCAgEAnVV9/Cqt4SwfZwExJFvhnnJL/Klv6lwU
// SIG // tj5OR2R4sQaTlz0xM7U518JxNj/aZGx80HU5bbsPMeTC
// SIG // j/ts0aGUGCLu6WZnOlNN3Zi6th542DYunKmCVgADsAW+
// SIG // iehp4LoJ7nvfam++Kctu2D9IdQHZGN5tggz1bSNU5HhT
// SIG // dSRXud2f8449xvNo32X2pFaq95W2KFUn0CS9QKC/GbYS
// SIG // EhFdPSfgQJY4rPf5KYnDvBewVIVCs/wMnosZiefwC2qB
// SIG // woEZQhlSdYo2wh3DYXMuLGt7bj8sCXgU6ZGyqVvfSaN0
// SIG // DLzskYDSPeZKPmY7T7uG+jIa2Zb0j/aRAfbOxnT99kxy
// SIG // bxCrdTDFNLB62FD+CljdQDzHVG2dY3RILLFORy3BFARx
// SIG // v2T5JL5zbcqOCb2zAVdJVGTZc9d/HltEAY5aGZFrDZ+k
// SIG // KNxnGSgkujhLmm77IVRrakURR6nxt67I6IleT53S0Ex2
// SIG // tVdUCbFpAUR+fKFhbHP+CrvsQWY9af3LwUFJfn6Tvsv4
// SIG // O+S3Fb+0zj6lMVGEvL8CwYKiexcdFYmNcP7ntdAoGokL
// SIG // jzbaukz5m/8K6TT4JDVnK+ANuOaMmdbhIurwJ0I9JZTm
// SIG // dHRbatGePu1+oDEzfbzL6Xu/OHBE0ZDxyKs6ijoIYn/Z
// SIG // cGNTTY3ugm2lBRDBcQZqELQdVTNYs6FwZvKhggNQMIIC
// SIG // OAIBATCB+aGB0aSBzjCByzELMAkGA1UEBhMCVVMxEzAR
// SIG // BgNVBAgTCldhc2hpbmd0b24xEDAOBgNVBAcTB1JlZG1v
// SIG // bmQxHjAcBgNVBAoTFU1pY3Jvc29mdCBDb3Jwb3JhdGlv
// SIG // bjElMCMGA1UECxMcTWljcm9zb2Z0IEFtZXJpY2EgT3Bl
// SIG // cmF0aW9uczEnMCUGA1UECxMeblNoaWVsZCBUU1MgRVNO
// SIG // OjdGMDAtMDVFMC1EOTQ3MSUwIwYDVQQDExxNaWNyb3Nv
// SIG // ZnQgVGltZS1TdGFtcCBTZXJ2aWNloiMKAQEwBwYFKw4D
// SIG // AhoDFQCD/QNkKDIW4VIF7j3oi2qbrR0a/6CBgzCBgKR+
// SIG // MHwxCzAJBgNVBAYTAlVTMRMwEQYDVQQIEwpXYXNoaW5n
// SIG // dG9uMRAwDgYDVQQHEwdSZWRtb25kMR4wHAYDVQQKExVN
// SIG // aWNyb3NvZnQgQ29ycG9yYXRpb24xJjAkBgNVBAMTHU1p
// SIG // Y3Jvc29mdCBUaW1lLVN0YW1wIFBDQSAyMDEwMA0GCSqG
// SIG // SIb3DQEBCwUAAgUA7h49xzAiGA8yMDI2MDgwNTIyNTUw
// SIG // M1oYDzIwMjYwODA2MjI1NTAzWjB3MD0GCisGAQQBhFkK
// SIG // BAExLzAtMAoCBQDuHj3HAgEAMAoCAQACAgJSAgH/MAcC
// SIG // AQACAhK9MAoCBQDuH49HAgEAMDYGCisGAQQBhFkKBAIx
// SIG // KDAmMAwGCisGAQQBhFkKAwKgCjAIAgEAAgMHoSChCjAI
// SIG // AgEAAgMBhqAwDQYJKoZIhvcNAQELBQADggEBAIz7Kv07
// SIG // Igrfh9eDV6OiX8A+PZb1KMm8OsJcVROmhzga0W7tC1iD
// SIG // 6DdDqB3W2tSY5bmt/VpJjZLFaLB+CNOD7GkC/xovPZ9X
// SIG // VqEJmzYLfRUjjHheNClPTBlUPOXThVR0D0qizSztJmaV
// SIG // Czl27hkaB3DfcSuAuBRkKgtADoeGifqt9OEFLsyE/tp4
// SIG // KJQarkgMVD45Hkz30Rh8ZZbSu0A8iw10Hum8FLKg2ltz
// SIG // XokdXY5AM1xpk5X/IBtUtzUMVG8jRukDS9+RziLhVoT+
// SIG // Th3OlUdu4MvLtXt6ROtbukcKSn1SYrZ3n+jY910zf9hM
// SIG // 62EivH57b34ecF+m51E5WZONxYgxggQNMIIECQIBATCB
// SIG // kzB8MQswCQYDVQQGEwJVUzETMBEGA1UECBMKV2FzaGlu
// SIG // Z3RvbjEQMA4GA1UEBxMHUmVkbW9uZDEeMBwGA1UEChMV
// SIG // TWljcm9zb2Z0IENvcnBvcmF0aW9uMSYwJAYDVQQDEx1N
// SIG // aWNyb3NvZnQgVGltZS1TdGFtcCBQQ0EgMjAxMAITMwAA
// SIG // Ah6jrKRuOW98SQABAAACHjANBglghkgBZQMEAgEFAKCC
// SIG // AUowGgYJKoZIhvcNAQkDMQ0GCyqGSIb3DQEJEAEEMC8G
// SIG // CSqGSIb3DQEJBDEiBCDemO/wMRSJNvYPGhrz7FDTBXoo
// SIG // BG5T+Uw2Gc5lnJ3sujCB+gYLKoZIhvcNAQkQAi8xgeow
// SIG // gecwgeQwgb0EIC+BXWrz9geMgM8Bvn8bqxHjhHXJ29EB
// SIG // izITIw0B9vOCMIGYMIGApH4wfDELMAkGA1UEBhMCVVMx
// SIG // EzARBgNVBAgTCldhc2hpbmd0b24xEDAOBgNVBAcTB1Jl
// SIG // ZG1vbmQxHjAcBgNVBAoTFU1pY3Jvc29mdCBDb3Jwb3Jh
// SIG // dGlvbjEmMCQGA1UEAxMdTWljcm9zb2Z0IFRpbWUtU3Rh
// SIG // bXAgUENBIDIwMTACEzMAAAIeo6ykbjlvfEkAAQAAAh4w
// SIG // IgQgVVUFkonGbWwAsjy3fug0iBRXTDL+/Be8sA5/sxPN
// SIG // +/0wDQYJKoZIhvcNAQELBQAEggIAf3TY2fWfNFhzY1kD
// SIG // rzQXkRP9LstguwfKeNstvLIcbixrKbTPoLueKVE4gfwH
// SIG // MloQ0qoTmB6+7qXDtLl2XsfJcL/fMh9musrXV5ZshUhu
// SIG // e+CvU5u/ZgrDx3HBfAuqSho02XT/eekLStSpnGfbr0Za
// SIG // aBtSkB96pC2L08FZ+bKmCL9DS2BRM5aLIw6+zdXPBX9/
// SIG // wPa42fjXON9zICN1CS79C/r7odalq8hmgP43Tp9yyy6/
// SIG // 5lDjpRpmxmqI1TQhI6rktM2zehfzE+g/a2FZFnBuDfdC
// SIG // T1IiX0GyeLYxTei2I8J2j6hh03kz+IYnBu9hYkAeHAcQ
// SIG // fgO88QQbzn6MZDh5z5TbPFGn3h7KCB/aJUH5nhl/gtUA
// SIG // BOmmQdlwl4s9/yfZqGALzSiygZ6we8Y5eK9UnzUYPnFS
// SIG // FykpfKLL0hn7KNdp0+8lHVMg/2qbYgifdNSC4rEivSGf
// SIG // unDllLxZgC3/dw4sM7x+EraFyPdv7kow5h+SqjBR46qh
// SIG // vVG/uJDEIcEw4ob4UhyOt5YQz5fj8a4lJf63YmniKqew
// SIG // fvTNCtkd4mQWZixAlrSxRbyIhz8185CNRtPY/B97B0Nr
// SIG // E4YNOres+QkP/R5gIXQMboVwbod8eylus+iOhWQjgX/y
// SIG // AvxtpTbgVP0LCETq2z1OUX/sZXrovHNXrbFjR23QLlAV
// SIG // LySBxgY=
// SIG // End signature block
