const relations=[
 {value:'auto-closed',label:'auto-closed',menuLabel:'Auto-closed',basicRoot:true,positive:{autoClosedAt:{null:false}},negative:{autoClosedAt:{null:true}}},
 {value:'parent',label:'parent issue',menuLabel:'Parent issues',positive:{children:{length:{gt:0}}},negative:{children:{length:{eq:0}}}},
 {value:'child',label:'sub-issue',menuLabel:'Sub-issues',positive:{parent:{null:false}},negative:{parent:{null:true}}},
 {value:'blocked',label:'blocked',menuLabel:'Blocked issues',positive:{hasBlockedByRelations:{eq:true}},negative:{hasBlockedByRelations:{eq:false}}},
 {value:'blocking',label:'blocking',menuLabel:'Blocking issues',positive:{hasBlockingRelations:{eq:true}},negative:{hasBlockingRelations:{eq:false}}},
 {value:'related',label:'relations',menuLabel:'Issues with relations',positive:{hasRelatedRelations:{eq:true}},negative:{hasRelatedRelations:{eq:false}}},
 {value:'duplicate',label:'issue with duplicate',menuLabel:'Duplicates',positive:{hasDuplicateRelations:{eq:true}},negative:{hasDuplicateRelations:{eq:false}}},
];
export function issueRelationField(){return {
 label:'Issue',basicLabel:'Relations',key:'issue-relation',type:'single',defaultOperator:'is',options:relations,operators:['is','not'],
 read(node){for(const option of relations)for(const [key,condition] of [['is',option.positive],['not',option.negative]])if(JSON.stringify(node)===JSON.stringify(condition))return {[key]:option.value};},
 build(operator,value){const option=relations.find(x=>x.value===value);if(!option)throw Error('Invalid issue relation filter');return structuredClone(operator==='not'?option.negative:option.positive);},
 operatorLabel(op,value){return (Array.isArray(value)?value[0]:value)==='related'?(op==='not'?'has no':'has'):op==='not'?'is not':'is';},
};}
