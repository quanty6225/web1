/* Bounded arithmetic parser. Cell contents are never executed as JavaScript. */
function workCalculate(cells){
 const cache=new Map(),active=new Set();let budget=40000;
 const numeric=v=>{if(v==='')return 0;const n=Number(v);if(!Number.isFinite(n))throw Error('#VALUE!');return n};
 function cell(row,col){
  if(--budget<0)throw Error('#LIMIT!');
  if(row<0||col<0||row>=cells.length||col>=cells[0].length)throw Error('#REF!');
  const key=row+':'+col;if(cache.has(key))return cache.get(key);
  if(active.has(key))throw Error('#CYCLE!');if(active.size>100)throw Error('#LIMIT!');
  const raw=cells[row][col];if(!raw.startsWith('='))return raw;
  active.add(key);
  try{const value=parse(raw.slice(1));cache.set(key,value);return value}finally{active.delete(key)}
 }
 function parse(source){
  if(source.toUpperCase().includes('#REF!'))throw Error('#REF!');
  const compact=source.replace(/\s+/g,'').toUpperCase(),tokens=compact.match(/(?:\d+(?:\.\d*)?|\.\d+)(?:E[+-]?\d+)?|\$?[A-Z]\$?[1-9]\d*|[A-Z]+|[()+\-*/,\:]/g)||[];
  if(tokens.join('')!==compact||tokens.length>500)throw Error('#VALUE!');let pos=0;
  function take(t){if(tokens[pos]===t){pos++;return true}return false}
  function ref(t){const m=/^\$?([A-Z])\$?([1-9]\d*)$/.exec(t||'');return m?[+m[2]-1,m[1].charCodeAt(0)-65]:null}
  function atom(){
   if(take('+'))return numeric(atom());if(take('-'))return -numeric(atom());
   if(take('(')){const v=add();if(!take(')'))throw Error('#VALUE!');return v}
   const token=tokens[pos++];if(token===undefined)throw Error('#VALUE!');
   const reference=ref(token);if(reference)return cell(...reference);
   if(/^\d|^\./.test(token))return numeric(token);
   if(!['SUM','AVERAGE','MIN','MAX','COUNT'].includes(token))throw Error('#NAME?');
   if(!take('('))throw Error('#VALUE!');const values=[];
   if(!take(')')){do{
    const first=ref(tokens[pos]);
    if(first&&tokens[pos+1]===':'){
     const last=ref(tokens[pos+2]);if(!last)throw Error('#REF!');pos+=3;
     if(last[0]>=cells.length||last[1]>=cells[0].length||first[0]>=cells.length||first[1]>=cells[0].length)throw Error('#REF!');
     for(let r=Math.min(first[0],last[0]);r<=Math.max(first[0],last[0]);r++)for(let c=Math.min(first[1],last[1]);c<=Math.max(first[1],last[1]);c++)values.push(cell(r,c));
    }else values.push(add());
   }while(take(','));if(!take(')'))throw Error('#VALUE!')}
   const nums=values.filter(v=>v!==''&&Number.isFinite(Number(v))).map(Number);
   if(token==='COUNT')return nums.length;
   if(token==='AVERAGE'){if(!nums.length)throw Error('#DIV/0!');return nums.reduce((a,b)=>a+b,0)/nums.length}
   if(token==='SUM')return nums.reduce((a,b)=>a+b,0);
   return nums.length?(token==='MIN'?Math.min(...nums):Math.max(...nums)):0;
  }
  function multiply(){let value=atom();while(['*','/'].includes(tokens[pos])){const op=tokens[pos++],right=numeric(atom());if(op==='/'&&!right)throw Error('#DIV/0!');value=op==='*'?numeric(value)*right:numeric(value)/right}return value}
  function add(){let value=multiply();while(['+','-'].includes(tokens[pos])){const op=tokens[pos++],right=numeric(multiply());value=op==='+'?numeric(value)+right:numeric(value)-right}return value}
  const value=add();if(pos!==tokens.length)throw Error('#VALUE!');return numeric(value);
 }
 return cells.map((row,r)=>row.map((_,c)=>{try{return cell(r,c)}catch(error){return error.message.startsWith('#')?error.message:'#VALUE!'}}));
}
