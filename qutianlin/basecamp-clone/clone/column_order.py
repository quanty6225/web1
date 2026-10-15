"""One persistent order for the ordinary columns of each Card Table."""
from lxml import html
from fastapi import HTTPException


def workflow(columns, board, include_inactive=False):
    from card_table import DATA, is_special, parent_columns
    from column_lifecycle import status
    parents = parent_columns(columns)
    source_rank = {identifier: index for index, identifier in enumerate(DATA['columns'])}
    selected = [column for identifier, column in columns.items()
                if column['board'] == board and not column.get('deleted')
                and identifier not in parents and not is_special(column)
                and (include_inactive or status(columns, identifier, parents) == 'active')]

    def initial_rank(column):
        # Existing local boards retain the source shell's original ID in HTML.
        identifier = column['id']
        if column.get('html'):
            identifier = html.fromstring(column['html']).get('id', '').removeprefix('recording_')
        return source_rank.get(identifier, len(source_rank))

    selected.sort(key=initial_rank)
    fallback = {column['id']: index for index, column in enumerate(selected, 1)}
    return sorted(selected, key=lambda column: column.get('position', fallback[column['id']]))


def move(connection, owner, columns, source, target, position):
    from card_table import save_column, is_special, parent_columns
    if source.get('deleted'):
        raise HTTPException(404, 'Column not found')
    from column_lifecycle import require_active
    require_active(columns, source['id'])
    if is_special(source) or source['id'] in parent_columns(columns):
        raise HTTPException(409, 'Only workflow columns can be reordered.')
    if target != source['board'].rsplit('/', 1)[-1]:
        raise HTTPException(404, 'Card Table not found')
    ordered = workflow(columns, source['board'])
    ordered = [column for column in ordered if column['id'] != source['id']]
    ordered.insert(min(position - 1, len(ordered)), source)
    # The caller holds BEGIN IMMEDIATE: all affected positions commit together.
    for index, column in enumerate(ordered, 1):
        save_column(connection, owner, {**column, 'position': index})


def render(tree, columns, board):
    for container in tree.xpath('//*[@id="kanban-workflow"]'):
        nodes = {node.get('data-kanban-column-id-value'): node for node in container}
        for column in workflow(columns, board):
            node = nodes.get(column['id'])
            if node is not None:
                container.append(node)
