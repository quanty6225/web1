"""Export saved rich content, resolving images only through the workspace resolver."""
from io import BytesIO
from pathlib import Path
from html import escape
from html.parser import HTMLParser
from threading import Lock

_font_lock = Lock()

class Node:
    def __init__(self, tag='', attrs=None):
        self.tag=tag;self.attrs=dict(attrs or []);self.children=[]
    def text(self):return ''.join(child if isinstance(child,str) else child.text() for child in self.children)

class Tree(HTMLParser):
    def __init__(self):super().__init__(convert_charrefs=True);self.root=Node();self.stack=[self.root]
    def handle_starttag(self,tag,attrs):
        node=Node(tag,attrs);self.stack[-1].children.append(node)
        if tag not in ('img','br','hr','source'):self.stack.append(node)
    def handle_endtag(self,tag):
        for index in range(len(self.stack)-1,0,-1):
            if self.stack[index].tag==tag:self.stack=self.stack[:index];break
    def handle_data(self,value):self.stack[-1].children.append(value)


def export_pdf(document,resolve_image=None,origin=''):
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.colors import HexColor,white
    from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Image,Table,TableStyle,HRFlowable
    from PIL import Image as PILImage

    root=Path(__file__).resolve().parent
    with _font_lock:
        if 'DocumentInter' not in pdfmetrics.getRegisteredFontNames():
            for name,file in [('DocumentInter','Inter-Regular.ttf'),('DocumentInter-Bold','Inter-Bold.ttf'),('DocumentInter-Italic','InterItalic-Regular.ttf'),('DocumentInter-BoldItalic','InterItalic-Bold.ttf')]:
                pdfmetrics.registerFont(TTFont(name,str(root/'document-fonts'/file)))
            pdfmetrics.registerFontFamily('DocumentInter',normal='DocumentInter',bold='DocumentInter-Bold',italic='DocumentInter-Italic',boldItalic='DocumentInter-BoldItalic')
            pdfmetrics.registerFont(UnicodeCIDFont('STSong-Light'))
    def text(value):
        chunks=[];current=[];wide=None
        for character in value:
            is_wide=ord(character)>=0x2e80
            if wide is not None and is_wide!=wide:
                result=escape(''.join(current));chunks.append('<font name="STSong-Light">'+result+'</font>' if wide else result);current=[]
            wide=is_wide;current.append(character)
        if current:
            result=escape(''.join(current));chunks.append('<font name="STSong-Light">'+result+'</font>' if wide else result)
        return ''.join(chunks)
    normal=ParagraphStyle('Document',fontName='DocumentInter',fontSize=10,leading=15,spaceAfter=8,textColor=HexColor('#202124'),splitLongWords=True)
    styles={tag:ParagraphStyle(tag,parent=normal,fontName='DocumentInter-Bold',fontSize=size,leading=size*1.35,spaceBefore=12,keepWithNext=True) for tag,size in [('h1',22),('h2',18),('h3',15),('h4',12)]}
    styles['pre']=ParagraphStyle('Code',parent=normal,fontName='Courier',fontSize=9,leading=13,backColor=HexColor('#f4f5f7'),borderPadding=8,spaceBefore=6,spaceAfter=12)
    styles['blockquote']=ParagraphStyle('Quote',parent=normal,leftIndent=14,borderColor=HexColor('#d4d4d8'),borderWidth=1,borderPadding=8,textColor=HexColor('#63636c'))
    styles['cell']=ParagraphStyle('Cell',parent=normal,fontSize=9,leading=13,spaceAfter=3)
    blocks={'p','div','h1','h2','h3','h4','blockquote','pre','ul','ol','li','table','hr','img','video','audio'}
    def inline(node):
        if isinstance(node,str):return text(node)
        value=''.join(inline(child) for child in node.children)
        tags={'strong':'b','b':'b','em':'i','i':'i','u':'u','s':'strike','strike':'strike'}
        if node.tag in tags:return '<'+tags[node.tag]+'>'+value+'</'+tags[node.tag]+'>'
        if node.tag=='br':return '<br/>'
        if node.tag=='code':return '<font name="Courier">'+value+'</font>'
        if node.tag=='a' and node.attrs.get('href','').startswith('/'):
            return '<a href="'+escape(origin+node.attrs['href'],quote=True)+'" color="#575bc7">'+value+'</a>' if origin else value
        return value
    def paragraph(value,style=normal):return Paragraph(value or '&#160;',style)
    def image(node,width):
        content=resolve_image(node.attrs.get('src','')) if resolve_image else None
        if content:
            try:
                with PILImage.open(BytesIO(content)) as source:
                    source.seek(0);source.load();w,h=source.size
                    buffer=BytesIO();source.convert('RGBA' if 'A' in source.getbands() else 'RGB').save(buffer,format='PNG')
                preferred=float(node.attrs.get('data-display-width',node.attrs.get('width',w)))*.75
                scale=min(width/max(w,1),640/max(h,1),preferred/max(w,1),1)
                result=Image(BytesIO(buffer.getvalue()),width=w*scale,height=h*scale);result.hAlign='LEFT';result.spaceAfter=10;return result
            except (OSError,ValueError,PILImage.DecompressionBombError):pass
        return paragraph(text(node.attrs.get('alt') or 'Image unavailable'),styles['blockquote'])
    def table(node,width):
        rows=[]
        def collect(parent):
            for child in parent.children:
                if isinstance(child,str):continue
                if child.tag=='tr':rows.append(child)
                elif child.tag in ('thead','tbody','tfoot'):collect(child)
        collect(node)
        if not rows:return []
        grid={};spans=[];headers=[];cols=0
        for y,row in enumerate(rows):
            x=0
            for cell in row.children:
                if isinstance(cell,str) or cell.tag not in ('td','th'):continue
                while (x,y) in grid:x+=1
                col=min(20,int(cell.attrs.get('colspan',1)));span=min(len(rows)-y,int(cell.attrs.get('rowspan',1)))
                grid[x,y]=cell
                for dx in range(col):
                    for dy in range(span):
                        if dx or dy:grid[x+dx,y+dy]=None
                if col>1 or span>1:spans.append(('SPAN',(x,y),(x+col-1,y+span-1)))
                if cell.tag=='th':headers.append(('BACKGROUND',(x,y),(x+col-1,y+span-1),HexColor('#f1f2f4')))
                x+=col;cols=max(cols,x)
        if not cols:return []
        cols=min(cols,100);data=[]
        for y in range(len(rows)):
            row=[]
            for x in range(cols):
                cell=grid.get((x,y));row.append(render(cell.children,width/cols-14,styles['cell']) if cell else '')
            data.append(row)
        commands=[('GRID',(0,0),(-1,-1),.5,HexColor('#dedee3')),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),7),('RIGHTPADDING',(0,0),(-1,-1),7),('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6),*spans,*headers]
        result=Table(data,colWidths=[width/cols]*cols,repeatRows=1 if all(c.tag=='th' for c in rows[0].children if not isinstance(c,str)) else 0,hAlign='LEFT',splitByRow=1,splitInRow=1)
        result.setStyle(TableStyle(commands));result.spaceAfter=12;return [result]
    def render(nodes,width,style=normal,depth=0):
        result=[];pending=[]
        def flush():
            if pending:
                value=''.join(pending)
                if value.strip():result.append(paragraph(value,style))
                pending.clear()
        for node in nodes:
            if isinstance(node,str) or node.tag not in blocks:pending.append(inline(node));continue
            flush();tag=node.tag
            if tag=='img':result.append(image(node,width))
            elif tag=='table':result.extend(table(node,width))
            elif tag in ('ul','ol'):
                count=0
                for item in node.children:
                    if isinstance(item,str)or item.tag!='li':continue
                    count+=1;bullet=('[x]' if item.attrs.get('data-done')=='true' else '[ ]') if item.attrs.get('data-type')=='todo_item' else str(count)+'.' if tag=='ol' else '•'
                    children=render(item.children,width-18,style,depth+1)
                    if not children:children=[paragraph('')]
                    row=Table([[paragraph(text(bullet),style),children]],colWidths=[18,width-18],hAlign='LEFT',splitInRow=1);row.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),0),('RIGHTPADDING',(0,0),(-1,-1),0),('TOPPADDING',(0,0),(-1,-1),0),('BOTTOMPADDING',(0,0),(-1,-1),0)]));result.append(row)
            elif tag=='pre':
                lines=node.text().split('\n');result.extend(paragraph(text(line).replace(' ','&#160;') or '&#160;',styles['pre']) for line in lines)
            elif tag=='hr':result.extend([HRFlowable(width='100%',color=HexColor('#dedee3'),spaceBefore=8,spaceAfter=10)])
            elif tag in ('audio','video'):result.append(paragraph(text(tag.capitalize()+' attachment'),styles['blockquote']))
            elif tag=='div' and node.attrs.get('data-callout')=='true':
                contents=render(node.children,width-20,style,depth);box=Table([[contents or paragraph('')]],colWidths=[width]);box.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),HexColor('#f4f5f7')),('BOX',(0,0),(-1,-1),.5,HexColor('#dedee3')),('LEFTPADDING',(0,0),(-1,-1),10),('RIGHTPADDING',(0,0),(-1,-1),10)]));box.spaceAfter=10;result.append(box)
            else:result.extend(render(node.children,width,styles.get(tag,style),depth))
        flush();return result
    tree=Tree();tree.feed(document.get('content_html',''));tree.close();output=BytesIO();pdf=SimpleDocTemplate(output,title=document['title'],author=document.get('last_editor',''),leftMargin=50,rightMargin=50,topMargin=48,bottomMargin=48)
    story=[paragraph(text(document['title']),ParagraphStyle('Title',parent=styles['h1'],spaceAfter=18)),*render(tree.root.children,pdf.width)]
    def footer(canvas,doc):
        canvas.saveState();canvas.setFont('DocumentInter',8);canvas.setFillColor(HexColor('#777780'));canvas.drawRightString(doc.pagesize[0]-50,25,str(doc.page));canvas.restoreState()
    pdf.build(story,onFirstPage=footer,onLaterPages=footer);return output.getvalue()
