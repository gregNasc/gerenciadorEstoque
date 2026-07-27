(function () {
    "use strict";

    const PAGE_SIZE = 12;

    function normalizeColumns(component, records) {
        if (Array.isArray(component.colunas) && component.colunas.length) {
            return component.colunas.map(function (column) {
                if (typeof column === "string") return {key: column, label: column};
                return {
                    key: column.chave || column.key || column.campo || column.label,
                    label: column.label || column.titulo || column.chave || column.key,
                };
            }).filter(function (column) { return column.key; });
        }
        const first = records.find(function (record) {
            return record && typeof record === "object" && !Array.isArray(record);
        });
        return first ? Object.keys(first).filter(function (key) {
            return !key.startsWith("_");
        }).map(function (key) { return {key: key, label: key}; }) : [];
    }

    function textValue(value) {
        if (value === null || value === undefined || value === "") return "-";
        if (typeof value === "object") return JSON.stringify(value);
        return String(value);
    }

    class ToryResults {
        constructor(options) {
            this.empty = options.empty;
            this.container = options.container;
            this.content = options.content;
            this.title = options.title;
            this.summary = options.summary;
            this.total = options.total;
            this.count = options.count;
            this.search = options.search;
            this.pagination = options.pagination;
            this.response = null;
            this.query = "";
            this.page = 1;
            this.sortKey = "";
            this.sortDirection = "asc";

            this.search.addEventListener("input", () => {
                this.query = this.search.value.trim().toLocaleLowerCase("pt-BR");
                this.page = 1;
                this.render();
            });
            this.content.addEventListener("click", (event) => {
                const button = event.target.closest("[data-tory-sort]");
                if (!button) return;
                const key = button.dataset.torySort;
                if (this.sortKey === key) this.sortDirection = this.sortDirection === "asc" ? "desc" : "asc";
                else {
                    this.sortKey = key;
                    this.sortDirection = "asc";
                }
                this.render();
            });
            this.pagination.addEventListener("click", (event) => {
                const button = event.target.closest("[data-tory-page]");
                if (!button || button.disabled) return;
                this.page = Number(button.dataset.toryPage) || 1;
                this.render();
            });
        }

        setResponse(response) {
            this.response = response;
            this.query = "";
            this.page = 1;
            this.sortKey = "";
            this.search.value = "";
            this.render();
        }

        clear() {
            this.response = null;
            this.content.replaceChildren();
            this.pagination.replaceChildren();
            this.container.classList.add("d-none");
            this.empty.classList.remove("d-none");
            this.count.classList.add("d-none");
            this.count.textContent = "0";
        }

        components() {
            return this.response ? window.ToryRenderer.structuredComponents(this.response) : [];
        }

        tables() {
            return this.components().filter(function (component) { return component.tipo === "tabela"; });
        }

        filteredRecords(component) {
            let records = window.ToryRenderer.recordsOf(component).slice();
            if (this.query) {
                records = records.filter((record) => Object.entries(record || {}).some(([key, value]) =>
                    !key.startsWith("_") && textValue(value).toLocaleLowerCase("pt-BR").includes(this.query)
                ));
            }
            if (this.sortKey) {
                const direction = this.sortDirection === "asc" ? 1 : -1;
                records.sort((left, right) => textValue(left[this.sortKey]).localeCompare(
                    textValue(right[this.sortKey]), "pt-BR", {numeric: true, sensitivity: "base"}
                ) * direction);
            }
            return records;
        }

        renderTable(component, primary) {
            const records = this.filteredRecords(component);
            const columns = normalizeColumns(component, records);
            const wrapper = window.ToryRenderer.element("div", "mb-3");
            if (component.titulo) wrapper.appendChild(window.ToryRenderer.element("h4", "h6 mb-2", component.titulo));
            const tableWrap = window.ToryRenderer.element("div", "tory-table-wrap");
            const table = window.ToryRenderer.element("table", "table table-hover tory-table");
            const thead = document.createElement("thead");
            const headRow = document.createElement("tr");
            columns.forEach((column) => {
                const th = document.createElement("th");
                th.scope = "col";
                const button = window.ToryRenderer.element("button", "tory-sort-button");
                button.type = "button";
                button.dataset.torySort = column.key;
                button.appendChild(document.createTextNode(column.label));
                if (this.sortKey === column.key) {
                    button.appendChild(window.ToryRenderer.icon(this.sortDirection === "asc" ? "arrow-up" : "arrow-down"));
                }
                th.appendChild(button);
                headRow.appendChild(th);
            });
            thead.appendChild(headRow);
            table.appendChild(thead);

            const tbody = document.createElement("tbody");
            const pageCount = Math.max(1, Math.ceil(records.length / PAGE_SIZE));
            if (this.page > pageCount) this.page = pageCount;
            const visible = primary ? records.slice((this.page - 1) * PAGE_SIZE, this.page * PAGE_SIZE) : records;
            visible.forEach(function (record) {
                const row = document.createElement("tr");
                columns.forEach(function (column) {
                    const cell = document.createElement("td");
                    cell.dataset.label = column.label;
                    const value = textValue(record && record[column.key]);
                    const cellAction = record && record._acoes_celulas && record._acoes_celulas[column.key];
                    if (cellAction && cellAction.pergunta) {
                        const button = window.ToryRenderer.element("button", "tory-cell-action", value);
                        button.type = "button";
                        button.dataset.toryQuestion = String(cellAction.pergunta).slice(0, 2000);
                        button.setAttribute("aria-label", "Consultar " + (cellAction.label || value));
                        cell.appendChild(button);
                    } else {
                        cell.textContent = value;
                    }
                    row.appendChild(cell);
                });
                tbody.appendChild(row);
            });
            if (!visible.length) {
                const row = document.createElement("tr");
                const cell = window.ToryRenderer.element(
                    "td",
                    "text-center text-muted py-4",
                    component.mensagem_vazia || "Nenhum item foi encontrado para os filtros informados."
                );
                cell.colSpan = Math.max(columns.length, 1);
                row.appendChild(cell);
                tbody.appendChild(row);
            }
            table.appendChild(tbody);
            tableWrap.appendChild(table);
            wrapper.appendChild(tableWrap);
            if (primary) this.renderPagination(pageCount, records.length, component);
            return wrapper;
        }

        renderPagination(pageCount, recordsCount, component) {
            this.pagination.replaceChildren();
            if (pageCount <= 1) return;
            const previous = window.ToryRenderer.element("button", "btn btn-sm btn-outline-secondary", "Anterior");
            previous.type = "button";
            previous.dataset.toryPage = String(this.page - 1);
            previous.disabled = this.page <= 1;
            const next = window.ToryRenderer.element("button", "btn btn-sm btn-outline-secondary", "Próxima");
            next.type = "button";
            next.dataset.toryPage = String(this.page + 1);
            next.disabled = this.page >= pageCount;
            this.pagination.appendChild(previous);

            const pages = [];
            for (let page = 1; page <= pageCount; page += 1) {
                if (
                    page === 1 || page === pageCount ||
                    Math.abs(page - this.page) <= 2
                ) pages.push(page);
            }
            let lastPage = 0;
            pages.forEach((page) => {
                if (lastPage && page - lastPage > 1) {
                    this.pagination.appendChild(window.ToryRenderer.element("span", "tory-page-ellipsis", "…"));
                }
                const pageButton = window.ToryRenderer.element(
                    "button",
                    "btn btn-sm " + (page === this.page ? "btn-secondary" : "btn-outline-secondary"),
                    page
                );
                pageButton.type = "button";
                pageButton.dataset.toryPage = String(page);
                pageButton.setAttribute("aria-label", "Ir para a página " + page);
                if (page === this.page) pageButton.setAttribute("aria-current", "page");
                this.pagination.appendChild(pageButton);
                lastPage = page;
            });

            this.pagination.appendChild(next);
            this.pagination.appendChild(window.ToryRenderer.element(
                "span",
                "tory-page-summary",
                recordsCount + " " + (
                    recordsCount === 1 ?
                        (component.rotulo_total_singular || "item exibido") :
                        (component.rotulo_total || "itens exibidos")
                )
            ));
        }

        render() {
            const components = this.components();
            if (!this.response || !components.length) {
                this.clear();
                return;
            }
            this.empty.classList.add("d-none");
            this.container.classList.remove("d-none");
            this.content.replaceChildren();
            this.pagination.replaceChildren();

            const message = this.response.mensagem || this.response.resposta || "";
            const tableComponents = this.tables();
            const primaryTable = tableComponents[0] || {};
            this.title.textContent = this.response.titulo || primaryTable.titulo || "Detalhes da consulta";
            this.summary.textContent = message.split("\n")[0];
            const total = tableComponents.reduce(function (sum, table) {
                return sum + window.ToryRenderer.recordsOf(table).length;
            }, 0);
            const metadataTotal = Number(this.response.metadados && this.response.metadados.total);
            const displayTotal = metadataTotal > total ? metadataTotal : total;
            const metadata = this.response.metadados || {};
            const totalLabel = displayTotal === 1 ?
                (metadata.rotulo_total_singular || primaryTable.rotulo_total_singular || "item exibido") :
                (metadata.rotulo_total || primaryTable.rotulo_total || "itens exibidos");
            this.total.textContent = displayTotal + " " + totalLabel;
            this.count.textContent = String(displayTotal);
            this.count.classList.remove("d-none");

            components.filter(function (component) { return component.tipo === "indicador"; })
                .forEach((component) => this.content.appendChild(window.ToryRenderer.renderIndicator(component)));
            components.filter(function (component) { return component.tipo === "lista"; })
                .forEach((component) => this.content.appendChild(window.ToryRenderer.renderList(component)));
            tableComponents.forEach((component, index) => {
                this.content.appendChild(this.renderTable(component, index === 0));
            });
        }
    }

    window.ToryResults = ToryResults;
}());
