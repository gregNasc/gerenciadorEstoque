(function () {
    "use strict";

    function element(tag, className, text) {
        const node = document.createElement(tag);
        if (className) node.className = className;
        if (text !== undefined && text !== null) node.textContent = String(text);
        return node;
    }

    function icon(name) {
        const node = element("i", "bi bi-" + name);
        node.setAttribute("aria-hidden", "true");
        return node;
    }

    function character(state) {
        return element("span", "tory-character tory-character-" + (state || "neutral"));
    }

    function timeLabel(date) {
        return new Intl.DateTimeFormat("pt-BR", {
            hour: "2-digit",
            minute: "2-digit",
        }).format(date || new Date());
    }

    function messageShell(kind, date, characterState) {
        const article = element("article", "tory-message tory-message-" + kind);
        article.dataset.toryDynamic = "true";
        const avatar = element("div", "tory-message-avatar");
        avatar.setAttribute("aria-hidden", "true");
        avatar.appendChild(
            kind === "user" ? icon("person-fill") : character(characterState || "responding")
        );

        const content = element("div", "tory-message-content");
        const heading = element("div", "tory-message-heading");
        heading.appendChild(element("strong", "", kind === "user" ? "Você" : "Tory"));
        heading.appendChild(element("time", "", timeLabel(date)));
        content.appendChild(heading);
        article.appendChild(avatar);
        article.appendChild(content);
        return {article: article, content: content};
    }

    function userMessage(text, date) {
        const shell = messageShell("user", date);
        shell.content.appendChild(element("p", "tory-component-text", text));
        return shell.article;
    }

    function loadingMessage() {
        const shell = messageShell("bot", new Date(), "thinking");
        shell.article.dataset.toryLoading = "true";
        const loading = element("div", "tory-loading");
        const spinner = element("span", "spinner-border spinner-border-sm");
        spinner.setAttribute("aria-hidden", "true");
        loading.appendChild(spinner);
        loading.appendChild(element("span", "", "Tory está analisando a solicitação..."));
        shell.content.appendChild(loading);
        return shell.article;
    }

    function errorMessage(message, date) {
        const shell = messageShell("bot", date, "attention");
        const error = element("div", "tory-error");
        error.setAttribute("role", "alert");
        error.appendChild(icon("exclamation-circle"));
        error.appendChild(document.createTextNode(" " + message));
        shell.content.appendChild(error);
        return shell.article;
    }

    function normalizeComponents(data) {
        if (Array.isArray(data.componentes) && data.componentes.length) {
            return data.componentes.filter(function (component) {
                return component && typeof component === "object" && component.tipo;
            });
        }
        const text = data.mensagem || data.resposta || "Não consegui formar uma resposta agora.";
        return [{tipo: "texto", texto: text}];
    }

    function renderText(component) {
        const text = String(component.texto || component.mensagem || "");
        const wrapper = element("div", "tory-component tory-component-text");
        const sourceLines = [];
        const regularLines = [];
        text.split("\n").forEach(function (line) {
            if (line.trim().startsWith("Fonte:")) sourceLines.push(line.trim());
            else regularLines.push(line);
        });
        if (regularLines.join("\n").trim()) {
            wrapper.appendChild(document.createTextNode(regularLines.join("\n").trim()));
        }
        sourceLines.forEach(function (line) {
            wrapper.appendChild(element("small", "tory-component-source", line));
        });
        return wrapper;
    }

    function renderIndicator(component) {
        const grid = element("div", "tory-component tory-indicator-grid");
        const card = element("div", "tory-indicator");
        card.appendChild(element("span", "", component.titulo || "Indicador"));
        card.appendChild(element("strong", "", component.valor !== undefined ? component.valor : "-"));
        grid.appendChild(card);
        return grid;
    }

    function renderList(component) {
        const card = element("div", "tory-component tory-list-card");
        if (component.titulo) card.appendChild(element("h4", "", component.titulo));
        const list = element("ul");
        (Array.isArray(component.itens) ? component.itens : []).forEach(function (item) {
            const row = element("li");
            if (item && typeof item === "object") {
                row.appendChild(element("span", "", item.nome || item.label || "Item"));
                row.appendChild(element("span", "", item.valor !== undefined ? item.valor : ""));
            } else {
                row.appendChild(element("span", "", item));
            }
            list.appendChild(row);
        });
        card.appendChild(list);
        return card;
    }

    function recordsOf(component) {
        return Array.isArray(component.registros) ? component.registros :
            (Array.isArray(component.linhas) ? component.linhas : []);
    }

    function renderTablePreview(component) {
        const card = element("div", "tory-component tory-list-card");
        card.appendChild(element("h4", "", component.titulo || "Detalhes da consulta"));
        const list = element("ul");
        const row = element("li");
        const count = recordsOf(component).length;
        if (!count) {
            row.appendChild(element(
                "span",
                "",
                component.mensagem_vazia || "Nenhum item foi encontrado para os filtros informados."
            ));
        } else {
            const countLabel = count === 1 ?
                (component.rotulo_total_singular || "item exibido") :
                (component.rotulo_total || "itens exibidos");
            row.appendChild(element("span", "", countLabel));
            row.appendChild(element("span", "", count));
        }
        list.appendChild(row);
        card.appendChild(list);
        return card;
    }

    function safeInternalUrl(rawUrl) {
        if (!rawUrl || typeof rawUrl !== "string") return null;
        try {
            const parsed = new URL(rawUrl, window.location.origin);
            if (parsed.origin !== window.location.origin) return null;
            return parsed.pathname + parsed.search + parsed.hash;
        } catch (error) {
            return null;
        }
    }

    function actionButton(label, iconName) {
        const button = element("button", "tory-message-action");
        button.type = "button";
        if (iconName) button.appendChild(icon(iconName));
        button.appendChild(document.createTextNode(label));
        return button;
    }

    function renderActions(container, data, question) {
        const actions = element("div", "tory-message-actions");
        const copy = actionButton("Copiar", "copy");
        copy.dataset.toryCopy = data.mensagem || data.resposta || "";
        actions.appendChild(copy);

        const favorite = actionButton("Favoritar", "star");
        favorite.dataset.toryFavorite = question || "";
        favorite.dataset.toryFavoriteAnswer = data.mensagem || data.resposta || "";
        actions.appendChild(favorite);

        if (hasStructuredResults(data)) {
            const results = actionButton("Abrir resultado completo", "arrows-angle-expand");
            results.dataset.toryOpenResults = "true";
            actions.appendChild(results);
        }

        const backendActions = [];
        (Array.isArray(data.acoes) ? data.acoes : []).forEach(function (action) {
            if (!action || typeof action !== "object") return;
            const label = String(action.label || action.pergunta || "").trim();
            if (!label) return;
            const internalUrl = safeInternalUrl(action.url);
            if (internalUrl) {
                const link = element("a", "tory-message-action");
                link.href = internalUrl;
                link.appendChild(icon("box-arrow-up-right"));
                link.appendChild(document.createTextNode(label));
                backendActions.push(link);
            } else if (action.tipo === "resultado" || action.codigo === "ver_resultados") {
                const resultAction = actionButton(label, "table");
                resultAction.dataset.toryOpenResults = "true";
                backendActions.push(resultAction);
            } else if (action.pergunta) {
                const questionAction = actionButton(label, "arrow-return-right");
                questionAction.dataset.toryQuestion = String(action.pergunta).slice(0, 2000);
                backendActions.push(questionAction);
            }
        });
        backendActions.slice(0, 6).forEach(function (node) { actions.appendChild(node); });
        if (backendActions.length > 6) {
            const more = element("details", "tory-more-actions");
            more.appendChild(element("summary", "", "Mostrar mais " + (backendActions.length - 6) + " opções"));
            const moreGrid = element("div", "tory-more-actions-grid");
            backendActions.slice(6).forEach(function (node) { moreGrid.appendChild(node); });
            more.appendChild(moreGrid);
            actions.appendChild(more);
        }
        container.appendChild(actions);
    }

    function botMessage(data, question, date) {
        const shell = messageShell("bot", date, "responding");
        normalizeComponents(data).forEach(function (component) {
            if (component.tipo === "texto") shell.content.appendChild(renderText(component));
            else if (component.tipo === "indicador") shell.content.appendChild(renderIndicator(component));
            else if (component.tipo === "lista") shell.content.appendChild(renderList(component));
            else if (component.tipo === "tabela") shell.content.appendChild(renderTablePreview(component));
            else if (component.tipo === "erro") shell.content.appendChild(renderText(component));
        });
        renderActions(shell.content, data, question);
        return shell.article;
    }

    function structuredComponents(data) {
        return normalizeComponents(data).filter(function (component) {
            return component.tipo === "tabela" ||
                (component.tipo === "lista" && Array.isArray(component.itens) && component.itens.length > 8) ||
                component.tipo === "indicador";
        });
    }

    function hasStructuredResults(data) {
        return normalizeComponents(data).some(function (component) {
            return component.tipo === "tabela" ||
                (component.tipo === "lista" && Array.isArray(component.itens) && component.itens.length > 8);
        });
    }

    window.ToryRenderer = {
        element: element,
        icon: icon,
        userMessage: userMessage,
        botMessage: botMessage,
        loadingMessage: loadingMessage,
        errorMessage: errorMessage,
        normalizeComponents: normalizeComponents,
        structuredComponents: structuredComponents,
        hasStructuredResults: hasStructuredResults,
        recordsOf: recordsOf,
        renderIndicator: renderIndicator,
        renderList: renderList,
    };
}());
