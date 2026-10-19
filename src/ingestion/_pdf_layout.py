"""PDF의 단별 읽기 순서와 보수적인 표 연결. OCR은 포함하지 않는다."""
import re


def word_rows(words, tolerance=3):
    rows = []
    for word in sorted(words, key=lambda w: (w['top'], w['x0'])):
        if not rows or abs(word['top'] - rows[-1][0]['top']) > tolerance:
            rows.append([word])
        else:
            rows[-1].append(word)
    return [sorted(row, key=lambda w: w['x0']) for row in rows]


def find_gutter(rows, width, height):
    """중앙 여백이 여러 행과 높이에서 반복될 때만 2단으로 추정한다."""
    candidates = []
    for row in rows:
        for left, right in zip(row, row[1:]):
            gap = right['x0'] - left['x1']
            mid = (left['x1'] + right['x0']) / 2
            if gap >= width * .035 and width * .35 < mid < width * .65:
                candidates.append((left['x1'], right['x0'], left['top']))
    best, support = None, []
    for ratio in range(35, 66):
        cut = width * ratio / 100
        matches = [(a, b, y) for a, b, y in candidates if a < cut < b]
        if len(matches) > len(support):
            best, support = cut, matches
    aligned = None
    if (len(support) >= 6 and len(support) >= len(rows) * .20
            and max(y for _, _, y in support)-min(y for _, _, y in support) >= height*.18):
        aligned = (max(a for a, _, _ in support) + min(b for _, b, _ in support)) / 2
    # 좌우 단의 줄 높이가 어긋나도 단 사이 세로 여백은 유지된다.
    # 머리말·꼬리말을 제외한 단어들의 x좌표 투영을 함께 검사한다.
    words = [w for row in rows for w in row if height*.09 < w['top'] < height*.93]
    options = []
    for ratio in range(40,61):
        cut = width*ratio/100
        left = [w for w in words if w['x1'] <= cut]
        right = [w for w in words if w['x0'] >= cut]
        crossing = [w for w in words if w['x0'] < cut < w['x1']]
        if min(len(left),len(right)) < 14 or len(crossing) > max(1,len(words)*.015):
            continue
        gap_left=max(w['x1'] for w in left)
        gap_right=min(w['x0'] for w in right)
        if gap_right-gap_left < width*.025:
            continue
        if min(max(w['top'] for w in side)-min(w['top'] for w in side) for side in (left,right)) < height*.18:
            continue
        options.append((len(crossing),-(gap_right-gap_left),(gap_left+gap_right)/2))
    if options:
        return min(options)[2]
    if aligned and sum(w['x0'] < aligned < w['x1'] for w in words) <= max(1,len(words)*.025):
        return aligned
    return None


def ordered_page_blocks(page, number):
    tables = page.find_tables()
    def in_table(w):
        x, y = (w['x0'] + w['x1'])/2, (w['top'] + w['bottom'])/2
        return any(a <= x <= c and b <= y <= d for a,b,c,d in (t.bbox for t in tables))
    words = [w for w in page.extract_words(extra_attrs=['size']) if not in_table(w)]
    rows = word_rows(words)
    cut = find_gutter(rows, page.width, page.height)
    # 표 위주의 별표 페이지는 본문 행이 적으므로 표 영역의 좌우 배치도 확인한다.
    if cut is None:
        left_tables = [t for t in tables if t.bbox[2] < page.width*.52 and t.bbox[0] < page.width*.30]
        right_tables = [t for t in tables if t.bbox[0] > page.width*.48 and t.bbox[2] > page.width*.70]
        if left_tables and right_tables:
            left_edge = max(t.bbox[2] for t in left_tables)
            right_edge = min(t.bbox[0] for t in right_tables)
            if right_edge-left_edge >= page.width*.025:
                cut = (left_edge+right_edge)/2
    blocks = []
    def emit(row, column):
        if not row:
            return
        blocks.append({'type':'line', 'text':' '.join(w['text'] for w in row),
            'location':{'page':number, 'bbox':[min(w['x0'] for w in row), min(w['top'] for w in row),
                                             max(w['x1'] for w in row), max(w['bottom'] for w in row)]},
            'page_height':page.height, 'page_width':page.width,
            'font_size':max(w.get('size',0) for w in row), 'column':column})
    for row in rows:
        if cut and any(w['x0'] < cut < w['x1'] for w in row):
            emit(row, 'full')
            continue
        left = [w for w in row if (w['x0']+w['x1'])/2 < (cut or page.width)]
        right = [w for w in row if w not in left]
        if cut and left and right and right[0]['x0']-left[-1]['x1'] >= page.width*.025:
            emit(left, 'left')
            emit(right, 'right')
        elif cut and left and right:
            emit(row, 'full')
        else:
            emit(row, 'right' if cut and right else ('left' if cut else 'full'))
    for table in tables:
        grid = table.extract()
        a,b,c,d = table.bbox
        column = 'full' if not cut or a < cut < c else ('left' if c <= cut else 'right')
        rows_meta = [{'page':number, 'cells':[list(cell) if cell else None for cell in row.cells]}
                     for row in table.rows]
        blocks.append({'type':'table', 'grid':grid,
            'text':'\n'.join(' | '.join(str(c or '') for c in row) for row in grid),
            'location':{'page':number,'bbox':list(table.bbox)}, 'source_locations':[{'page':number,'bbox':list(table.bbox)}],
            'row_sources':rows_meta, 'page_width':page.width,'page_height':page.height,'column':column})
    # 전체 너비 제목·표를 경계로 영역별 왼쪽→오른쪽 단을 읽는다.
    spanning = sorted([b for b in blocks if b['column']=='full'], key=lambda b:b['location']['bbox'][1]) if cut else []
    remaining = [b for b in blocks if b['column']!='full'] if cut else blocks[:]
    ordered = []
    for wide in spanning:
        before = [b for b in remaining if b['location']['bbox'][1] < wide['location']['bbox'][1]]
        ordered.extend(sorted(before, key=lambda b:(b['column']=='right', b['location']['bbox'][1])))
        remaining = [b for b in remaining if b not in before]
        ordered.append(wide)
    ordered.extend(sorted(remaining, key=lambda b:(b['column']=='right', b['location']['bbox'][1])))
    for i, block in enumerate(ordered):
        block['reading_order'] = i
        block['layout_columns'] = 2 if cut else 1
    return ordered, {'page':number, 'columns':2 if cut else 1, 'gutter_x':cut}


def column_edges(table):
    """셀 좌표로 표 내부 열 경계 비율을 구한다."""
    n = max(map(len, table['grid']), default=0)
    box = table['location']['bbox']
    width = box[2]-box[0]
    for row in table.get('row_sources', []):
        cells = row['cells']
        if len(cells)==n and all(cells) and width > 0:
            return [(cell[0]-box[0])/width for cell in cells] + [1.0]
    return None


def stitch_tables(blocks):
    """이웃한 표만 비교하고 동일 헤더나 연속 번호가 확인되면 연결한다."""
    result, decisions = [], []
    for block in blocks:
        previous = next((b for b in reversed(result) if not b.get('excluded_reason')), None)
        if block.get('excluded_reason') or block['type']!='table' or not previous or previous['type']!='table':
            result.append(block)
            continue
        prev_loc = previous.get('source_locations', [previous['location']])[-1]
        prev_page, page = prev_loc['page'], block['location']['page']
        cross = (page==prev_page and previous['column']=='left' and block['column']=='right') or page==prev_page+1
        edges1, edges2 = column_edges(previous), column_edges(block)
        same = (edges1 and edges2 and len(edges1)==len(edges2)
                and max(abs(a-b) for a,b in zip(edges1,edges2)) <= .035)
        last_box, box = prev_loc['bbox'], block['location']['bbox']
        near_ends = last_box[3] >= previous['page_height']*.70 and box[1] <= block['page_height']*.30
        width_matches = abs((last_box[2]-last_box[0])/previous['page_width']
                            - (box[2]-box[0])/block['page_width']) <= .04
        if not (cross and same and near_ends and width_matches):
            result.append(block)
            continue
        norm = lambda row: [re.sub(r'\s+','',str(c or '')) for c in row]
        repeated = norm(previous['grid'][0]) == norm(block['grid'][0])
        a, b = str(previous['grid'][-1][0] or '').strip(), str(block['grid'][0][0] or '').strip()
        digits_a, digits_b = re.fullmatch(r'(\d+)(호봉|급|번)?',a), re.fullmatch(r'(\d+)(호봉|급|번)?',b)
        sequential = bool(digits_a and digits_b and digits_a[2]==digits_b[2] and int(digits_b[1])==int(digits_a[1])+1)
        decision = {'from':prev_loc,'to':block['location'], 'status':'merged' if repeated or sequential else 'review_required',
                    'reason':'repeated_header' if repeated else 'sequential_key' if sequential else 'matching_geometry_only'}
        decisions.append(decision)
        if not (repeated or sequential):
            block['table_continuation_candidate'] = decision
            result.append(block)
            continue
        start = 1 if repeated else 0
        if start < len(block['grid']) and block['grid'][start] and not str(block['grid'][start][0] or '').strip():
            previous.setdefault('row_continuation_candidates', []).append({
                'previous_row': len(previous['grid'])-1,
                'next_row': len(previous['grid']),
                'reason': 'continuation_first_cell_blank',
                'review_required': True,
                'source_location': block['location']})
        previous['grid'].extend(block['grid'][start:])
        previous['row_sources'].extend(block['row_sources'][start:])
        previous['source_locations'].extend(block['source_locations'])
        previous['text'] = '\n'.join(' | '.join(str(c or '') for c in row) for row in previous['grid'])
        previous.setdefault('table_merge_decisions',[]).append(decision)
        previous['column'] = block['column']
        previous['page_height'] = block['page_height']
    return result, decisions
