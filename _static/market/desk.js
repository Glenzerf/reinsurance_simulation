// Shared view helpers. All data, including team names and imported research text, goes
// through textContent. The server makes every authorization and financial decision.
'use strict';
const desk = () => document.getElementById('desk');
function el(parent, tag, text) {
    const node=document.createElement(tag);
    if(text!==undefined) node.textContent=text;
    parent.append(node);
    return node;
}
function section(title) {
    const box=el(desk(),'section');
    el(box,'h2',title);
    return box;
}
function button(parent,title,fn) {
    const b=el(parent,'button',title);
    b.type='button'; b.onclick=fn; return b;
}
function field(parent,title,options,value) {
    const label=el(parent,'label',title);
    const node=el(label,Array.isArray(options)?'select':'input');
    if(Array.isArray(options)) for(const item of options) node.add(new Option(item || 'Inactive / unused',item));
    else {node.type=options; if(options==='number'){node.step='any';node.min='0';}}
    if(value!==undefined && value!==null) node.value=value;
    return node;
}
function table(parent,headers,rows) {
    const t=el(parent,'table'), h=el(el(t,'thead'),'tr'), body=el(t,'tbody');
    headers.forEach(x=>el(h,'th',x));
    rows.forEach(values=>{const tr=el(body,'tr'); values.forEach(x=>el(tr,'td',x??'—'));});
}
function caption(s) {
    return 'Phase · '+s.phase+'   |   Ledger '+s.book+(s.minutes?'   |   Target finish '+new Date(Date.parse(s.since)+s.minutes*60000).toLocaleTimeString():'');
}
function begin(msg) {
    desk().replaceChildren();
    document.getElementById('status').textContent=msg.error || '';
}
const pct=x=>x==null?'—':Number((100*x).toPrecision(12))+'%';
function money(x,s) {return x==null?'—':Number(x).toLocaleString('en-CA',{maximumFractionDigits:s.decimals});}
function ticketTable(parent,tickets) {
    if(!tickets.length){el(parent,'p','No tickets.');return;}
    table(parent,['Ticket','Parties','Line / structure','Share','Premium / fee ($m)','Package / requires','Status / signed by'],
        tickets.map(t=>[t.id+' v'+t.version,t.buyer+' / '+t.seller+' / '+t.broker,
            t.line+' · '+(t.kind==='QS'?'QS '+pct(t.q):'XOL '+t.limit+' above '+t.attachment),
            pct(t.share),t.premium+' / '+Number(t.fee.toPrecision(12)),[t.package,...t.requires].filter(Boolean).join(', '),
            t.status+' · '+Object.keys(t.signatures).join(', ')]));
}
const cashLabels={opening:'Opening contributed equity',direct:'Direct premium received',expenses:'Operating expenses',
    bought:'Treaty premiums paid',sold:'Treaty premiums received',fees_paid:'Broker fees paid',fees_earned:'Broker fees earned',
    funds:'Investable funds',H:'Portfolio gross payoff (multiple)',assets:'Year-end investment assets',gain:'Investment gain',
    gross:'Gross direct claims',promised:'Treaty claims promised',paid:'Treaty claims paid',promised_in:'Promised recoveries',
    recovered:'Actual recoveries',ratio:'Seller payment ratio',policyholders_paid:'Direct policyholder payments',
    shortfall:'Unpaid obligations',equity:'Signed ending equity / wealth',residual:'Shareholder residual',
    profit:'Accounting profit',roe:'ROE',assessment:'Post-class capital assessment'};
function statement(parent,values,s) {
    table(parent,['Item','Value ($m unless indicated)'],Object.entries(values).map(([k,v])=>
        [cashLabels[k]||k,['roe','ratio'].includes(k)?pct(v):typeof v==='number'?money(v,s):v]));
}
function brokerEditor(parent,s,send,t={}) {
    // Create and amendment share one editor. Fractions are typed explicitly here;
    // investment entry below instead uses percentages and converts exactly once.
    const details=el(parent,'details');
    el(details,'summary',t.id?'Amend '+t.id+' v'+t.version:'Enter a participation');
    const inputs={};
    const specs=[['buyer','Insurer',s.teams.filter(x=>x[0]==='I')],['seller','Reinsurer',s.teams.filter(x=>x[0]==='R')],
        ['line','Annual line',[...'ABCD']],['kind','Structure',['QS','XOL']],['q','QS fraction (0–1)','number'],
        ['attachment','XOL attachment ($m)','number'],['limit','XOL limit ($m)','number'],['share','Participation (0–1)','number'],
        ['premium','Premium ($m)','number'],['package','All-or-none package ID','text'],['requires','Required IDs, comma-separated','text']];
    for(const [k,title,type] of specs) inputs[k]=field(details,title,type,k==='requires'?(t.requires||[]).join(','):t[k]);
    const zero=field(details,'Confirm zero premium','checkbox');
    button(details,t.id?'Save revised proposal':'Record proposal',()=>{
        const data=Object.fromEntries(Object.entries(inputs).map(([k,input])=>[k,input.value]));
        data.requires=data.requires.split(',').map(x=>x.trim()).filter(Boolean);
        send(t.id?'amend':'propose',{...data,id:t.id,version:t.version,zero:zero.checked});
    });
}
function investments(s,send) {
    const box=section(s.phase==='invest'?'Final investment submission':'Portfolio allocation');
    el(box,'p','Investable funds: '+money(s.cash.funds,s)+' million. Enter percentages totaling 100.');
    const assets=['short','long','etf'];
    const titles=['One-year zero','Four-year zero','Equity ETF'];
    const inputs=assets.map((k,i)=>field(box,titles[i]+' (%)','number',s.weights?100*s.weights[i]:undefined));
    const amounts=el(box,'p');
    function preview(){amounts.textContent=titles.map((k,i)=>k+' $'+money(s.cash.funds*Number(inputs[i].value)/100,s)+'m').join('   ·   ');}
    inputs.forEach(input=>input.oninput=preview);preview();
    const editable=['trade','review','invest'].includes(s.phase);
    inputs.forEach(input=>input.disabled=!editable);
    if(editable) {
        const save=op=>{
            if(inputs.some(x=>x.value==='')){document.getElementById('status').textContent='Enter all three percentages, including zeros.';return;}
            send(op,Object.fromEntries(assets.map((k,i)=>[k,Number(inputs[i].value)/100])));
        };
        button(box,'Save draft',()=>save('draft'));
        if(s.phase==='invest') button(box,'Submit final allocation',()=>save('submit'));
    }
    el(box,'p',s.submitted?'Final allocation recorded.':s.weights?'Draft allocation on file.':'No allocation on file.');
    return box;
}
function capitalRule(parent,p) {
    el(parent,'p','Investors target '+pct(p.target)+' ROE. After class, insurers and reinsurers are assessed against the '+pct(p.solvency)+' solvency limit. Economic profit equals accounting profit less '+pct(p.ordinary_cost)+' of required capital and a further '+pct(p.shortfall_cost-p.ordinary_cost)+' of any positive shortfall versus opening equity. Original capital funds claims. Brokers are exempt.');
}
// A tab is local navigation only. A change of phase selects the classroom task for
// that phase; all other authorized views remain accessible without a page submission.
let activeTab='', lastPhase='';
function teamTabs(s,top,panels) {
    const nav=el(top,'nav');nav.setAttribute('aria-label','Team desk views');
    if(s.phase!==lastPhase) {
        activeTab=({trade:'Role sheet',review:'Whole book',invest:'Investments',frozen:'Investments',settled:'Results'})[s.phase];
        lastPhase=s.phase;
    }
    const buttons={};
    function show(key) {
        activeTab=key;
        for(const [name,node] of Object.entries(panels)){
            node.hidden=name!==key;
            buttons[name].setAttribute('aria-pressed',String(name===key));
        }
    }
    for(const key of Object.keys(panels))buttons[key]=button(nav,key,()=>show(key));
    show(panels[activeTab]?activeTab:'Role sheet');
}
function prospectiveBook(book,s) {
    const pending=s.tickets.filter(t=>t.status==='pending');
    if(!pending.length || s.phase!=='trade')return;
    const panel=el(book,'details');el(panel,'summary','Preview pending offers');
    el(panel,'p','Add offers to the signed book to preview inception cash. These choices are local to this screen.');
    const choices=pending.map(t=>[t,field(panel,t.id+' v'+t.version,'checkbox')]);
    const out=el(panel,'p');
    function recalc(){
        let funds=s.cash.funds;
        for(const [t,input] of choices)if(input.checked){
            if(s.role===t.buyer)funds-=t.premium+t.fee;
            if(s.role===t.seller)funds+=t.premium;
            if(s.role===t.broker)funds+=t.fee;
        }
        out.textContent='Hypothetical investable funds: $'+money(funds,s)+'m';
        if(s.weights)out.textContent+=' · investments ($m): '+s.weights.map(w=>money(w*funds,s)).join(' / ');
    }
    choices.forEach(([,input])=>input.onchange=recalc);recalc();
}
function renderTeam(msg) {
    const s=msg.state;begin(msg);
    const send=(op,p={})=>liveSend({...p,op,rev:s.rev});
    const top=section(s.role?s.label+(s.name?' · '+s.name:''):'Participant slot '+s.slot);
    el(top,'p',caption(s));button(top,'Refresh desk',()=>send('sync'));
    if(!s.role){capitalRule(top,s.public);el(top,'p','This slot has no active assignment. Refresh after the instructor opens trading.');return;}
    const name=field(top,'Optional team name','text',s.name);
    if(['trade','review','invest'].includes(s.phase)) button(top,'Save name',()=>send('name',{name:name.value}));
    const sheet=section('Private role sheet');
    el(sheet,'p',s.sheet.mandate);
    if(s.sheet.exposures)el(sheet,'p','Exposure multipliers · '+Object.entries(s.sheet.exposures).map(([k,v])=>k+' × '+v).join('   '));
    capitalRule(sheet,s.public);
    el(sheet,'p','Opening capital: $'+money(s.sheet.capital,s)+'m. Direct premium per insurer: $'+money(s.public.direct,s)+'m. Operating expenses per insurer: $'+money(s.public.expenses,s)+'m. The buyer pays brokerage of '+pct(s.public.brokerage)+' on each premium.');
    const assets=s.public.assets;
    table(sheet,['Asset','Inception price / distribution'],[
        ['One-year zero',1/(1+assets.short_yield)+' per unit face'],
        ['Four-year zero',1/(1+assets.long_yield)**(assets.remaining_years+1)+' per unit face; year-end yields '+assets.yields.map(pct).join(' / ')+' with probabilities '+assets.probabilities.map(pct).join(' / ')],
        ['ETF','Lognormal gross payoff; arithmetic mean '+assets.etf_mean+', SD '+assets.etf_sd]]);
    const law=s.public.loss;
    table(sheet,['Annual standard line','Public model'],[
        ['A · Homeowners','Poisson('+law.A.count+'); Gamma shape '+law.A.shape+', scale '+law.A.scale],
        ['B · Regional wildfire','Independent event '+pct(law.B.prob)+'; Pareto I minimum '+law.B.minimum+', shape '+law.B.shape],
        ['C · Product liability','Poisson('+law.C.count+'); lognormal arithmetic mean '+law.C.mean+', SD '+law.C.sd],
        ['D · Widespread flood','Shared event '+pct(law.D.prob)+' and shared Gamma severity, shape '+law.D.shape+', scale '+law.D.scale]]);

    const book=section('Whole book · '+s.book);
    ticketTable(book,s.tickets.filter(t=>['signed','bound'].includes(t.status)));
    statement(book,s.cash,s);prospectiveBook(book,s);
    if(s.phase==='review') button(book,s.confirmed?'Whole book confirmed':'Confirm whole book (including no trade)',()=>send('confirm',{book:s.book}));
    const tickets=section(s.role[0]==='B'?'Broker proposals':'Counterparty signatures');
    ticketTable(tickets,s.tickets);
    if(s.phase==='trade'){
        if(s.role[0]==='B')brokerEditor(tickets,s,send);
        for(const t of s.tickets.filter(t=>['pending','signed','rejected'].includes(t.status))){
            const exact={id:t.id,version:t.version};
            if(s.role===t.broker){
                brokerEditor(tickets,s,send,t);
                button(tickets,'Withdraw '+t.id,()=>send('withdraw',exact));
            }else if(t.status!=='rejected'){
                if(!t.signatures[s.role])button(tickets,'Approve '+t.id+' v'+t.version,()=>send('approve',exact));
                button(tickets,'Reject '+t.id+' v'+t.version,()=>send('reject',exact));
            }
        }
    }
    const panels={'Role sheet':sheet,'Tickets':tickets,'Whole book':book,'Investments':investments(s,send)};
    if(s.result){
        const out=section('Private settlement');
        panels.Results=out;statement(out,s.result,s);
        table(out,['Common financial outcome','Gross payoff / yield'],Object.entries(s.market).map(([k,v])=>[k,k==='yield_end'?pct(v):v]));
        if(Object.keys(s.losses).length)table(out,['Line','Scaled annual claims ($m)'],Object.entries(s.losses));
        if(Object.keys(s.payments).length)table(out,['Ticket','Buyer','Seller','Promised ($m)','Paid ($m)'],
            Object.entries(s.payments).map(([id,p])=>[id,p.buyer,p.seller,money(p.promised,s),money(p.paid,s)]));
    }
    teamTabs(s,top,panels);
}
function renderAdmin(msg,session) {
    // No guessed URL, participant role or client-side flag confers admin rights.
    // Every button sends the revision currently shown and the server repeats all checks.
    begin(msg);
    const s=msg.state, box=section(caption(s));
    const send=(op,p={})=>adminRequest({...p,op,rev:s.rev});
    button(box,'Refresh market',()=>adminRequest());
    if(s.phase==='setup'){
        const setup=section('Assign participant slots');
        const inputs=s.slots.map(k=>[k,field(setup,'Slot '+k,['',...s.roles],'')]);
        button(setup,'Fill in preset order',()=>inputs.forEach(([,input],i)=>input.value=s.roles[i]||''));
        button(setup,'Open trading with these assignments',()=>send('open',{assign:Object.fromEntries(inputs.filter(([,e])=>e.value).map(([k,e])=>[k,e.value]))}));
        return;
    }
    const roster=section('Attendance and outstanding decisions');
    table(roster,['Slot','Role','Team name','Whole book','Investment'],s.slots.map(slot=>{
        const r=s.assign[slot];
        return [slot,r||'Inactive',s.names[r],r?(s.missing_books.includes(r)?'Outstanding':'Confirmed'):'—',
                r?(s.missing_investments.includes(r)?'Outstanding':'Submitted'):'—'];
    }));
    if(['review','trade'].includes(s.phase)){
        const r=field(roster,'Remove active team',s.teams),reason=field(roster,'Reason','text');
        button(roster,'Invalidate affected tickets and remove',()=>{if(confirm('Remove this team, invalidate its provisional tickets and reopen trading?'))send('remove',{role:r.value,reason:reason.value});});
    }
    for(const [r,reviewed] of Object.entries(s.removal_reviews||{})){
        el(roster,'p','Removed '+r+' · '+s.removed[r]);
        if(!reviewed) button(roster,'Acknowledge invalidated tickets for '+r,()=>send('ack_remove',{role:r}));
    }
    const ledger=section('Ticket status and close checks');
    ticketTable(ledger,s.tickets);
    el(ledger,'p',s.issues.join('\n')||'No package, structure or funding conflicts in signed book.');
    const actions=section('Market controls');
    const next={trade:['review','Begin whole-book review'],review:['close','Bind signed book and expire incomplete offers'],
                invest:['freeze','Freeze all decisions'],frozen:['settle','Draw and settle once']}[s.phase];
    if(next)button(actions,next[1],()=>{if(confirm(next[1]+'?'))send(next[0]);});
    if(s.phase==='review')button(actions,'Reopen trading',()=>send('reopen'));
    if(s.phase==='frozen'){
        const reason=field(actions,'Unlock reason','text');
        button(actions,'Unlock and clear investment confirmations',()=>send('unlock',{reason:reason.value}));
    }
    el(actions,'p','Freeze ID · '+(s.freeze||'pending')+'   |   Settlement ID · '+(s.settlement||'pending'));
    const files=section('Download session CSVs');
    for(const name of ['contracts','investments','configuration','realization','settlement','ticket_payments','contract_history']){
        const link=el(files,'a',name+'.csv');link.href='/csv/'+encodeURIComponent(session)+'/'+name;el(files,'br');
    }
}
