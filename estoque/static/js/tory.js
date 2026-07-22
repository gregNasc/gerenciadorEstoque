(function () {
    "use strict";

    document.addEventListener("DOMContentLoaded", function () {
        const widget = document.getElementById("tory-widget");
        const modalElement = document.getElementById("tory-modal");
        if (!widget || !modalElement || !window.bootstrap || !window.ToryApi || !window.ToryRenderer) return;

        const elements = {
            widget: widget,
            minimized: document.getElementById("tory-minimized"),
            toggle: document.getElementById("tory-toggle"),
            modal: modalElement,
            form: document.getElementById("tory-form"),
            input: document.getElementById("tory-question"),
            submit: document.getElementById("tory-submit"),
            stop: document.getElementById("tory-stop"),
            processing: document.getElementById("tory-processing-label"),
            live: document.getElementById("tory-live-status"),
            messages: document.getElementById("tory-messages"),
            suggestions: document.getElementById("tory-suggestions"),
            tabs: Array.from(document.querySelectorAll("[data-tory-tab]")),
            panels: Array.from(document.querySelectorAll("[data-tory-panel]")),
            history: document.getElementById("tory-history"),
            historyEmpty: document.getElementById("tory-history-empty"),
            favorites: document.getElementById("tory-favorites"),
            favoritesEmpty: document.getElementById("tory-favorites-empty"),
            characters: Array.from(document.querySelectorAll("[data-tory-character]")),
        };
        const apiUrl = widget.dataset.toryApiUrl;
        const modal = window.bootstrap.Modal.getOrCreateInstance(modalElement, {
            backdrop: true,
            keyboard: true,
            focus: true,
        });

        const toryState = {
            aberta: false,
            minimizada: false,
            abaAtiva: "conversa",
            conversaId: null,
            processando: false,
            mensagens: [],
            resultadoAtual: null,
            paginaAtual: 1,
            historico: [],
            favoritos: [],
            requisicao: null,
            perguntaAtual: "",
            reinicioContexto: Promise.resolve(),
            falhaReinicioContexto: false,
            estadoVisual: "neutral",
        };
        let visualStateTimer = null;

        const results = new window.ToryResults({
            empty: document.getElementById("tory-results-empty"),
            container: document.getElementById("tory-results"),
            content: document.getElementById("tory-results-content"),
            title: document.getElementById("tory-results-title"),
            summary: document.getElementById("tory-results-summary"),
            total: document.getElementById("tory-results-total"),
            count: document.getElementById("tory-results-count"),
            search: document.getElementById("tory-results-search"),
            pagination: document.getElementById("tory-results-pagination"),
        });

        function setVisualState(state, resetAfter) {
            const validStates = ["neutral", "thinking", "responding", "attention", "success"];
            state = validStates.includes(state) ? state : "neutral";
            if (visualStateTimer) window.clearTimeout(visualStateTimer);
            visualStateTimer = null;
            toryState.estadoVisual = state;
            elements.characters.forEach(function (characterNode) {
                validStates.forEach(function (item) {
                    characterNode.classList.toggle("tory-character-" + item, item === state);
                });
            });
            if (resetAfter) {
                visualStateTimer = window.setTimeout(function () {
                    setVisualState("neutral");
                }, resetAfter);
            }
        }

        function responseNeedsAttention(data) {
            return data.sucesso === false || data.tipo === "erro" || (
                Array.isArray(data.componentes) && data.componentes.some(function (component) {
                    return component && component.tipo === "erro";
                })
            );
        }

        function announce(message) {
            elements.live.textContent = "";
            window.setTimeout(function () { elements.live.textContent = message; }, 10);
        }

        function activateTab(name, focusTab) {
            if (!elements.panels.some(function (panel) { return panel.dataset.toryPanel === name; })) return;
            toryState.abaAtiva = name;
            elements.tabs.forEach(function (tab) {
                const active = tab.dataset.toryTab === name;
                tab.classList.toggle("active", active);
                tab.setAttribute("aria-selected", String(active));
                tab.tabIndex = active ? 0 : -1;
                if (active && focusTab) tab.focus();
            });
            elements.panels.forEach(function (panel) {
                const active = panel.dataset.toryPanel === name;
                panel.classList.toggle("active", active);
                panel.hidden = !active;
            });
        }

        function scrollConversation() {
            const panel = document.getElementById("tory-panel-conversa");
            window.requestAnimationFrame(function () { panel.scrollTop = panel.scrollHeight; });
        }

        function addMessage(node) {
            elements.messages.appendChild(node);
            scrollConversation();
        }

        function setProcessing(active) {
            toryState.processando = active;
            elements.input.disabled = active;
            elements.submit.disabled = active;
            elements.processing.classList.toggle("d-none", !active);
            elements.stop.classList.toggle("d-none", !active);
            if (active) {
                setVisualState("thinking");
                announce("Tory está analisando a solicitação.");
            } else if (toryState.estadoVisual === "thinking") {
                setVisualState("neutral");
            }
        }

        function autoResize() {
            elements.input.style.height = "auto";
            elements.input.style.height = Math.min(elements.input.scrollHeight, 130) + "px";
        }

        function removeLoading() {
            const loading = elements.messages.querySelector("[data-tory-loading]");
            if (loading) loading.remove();
        }

        function responseSummary(data) {
            return String(data.mensagem || data.resposta || "").split("\n")[0].slice(0, 240);
        }

        function addHistory(question, data) {
            const item = {
                id: String(Date.now()) + String(Math.random()).slice(2),
                pergunta: question,
                resumo: responseSummary(data),
                data: new Date(),
                sucesso: data.sucesso !== false,
                resposta: data,
            };
            toryState.historico.unshift(item);
            renderHistory();
        }

        function createRecord(item, favoriteMode) {
            const article = window.ToryRenderer.element("article", "tory-record");
            const heading = window.ToryRenderer.element("div", "tory-record-heading");
            heading.appendChild(window.ToryRenderer.element("strong", "", item.pergunta));
            heading.appendChild(window.ToryRenderer.element(
                "time", "", new Intl.DateTimeFormat("pt-BR", {dateStyle: "short", timeStyle: "short"}).format(item.data)
            ));
            article.appendChild(heading);
            article.appendChild(window.ToryRenderer.element("p", "tory-record-summary", item.resumo));
            const actions = window.ToryRenderer.element("div", "tory-record-actions");
            const rerun = window.ToryRenderer.element("button", "btn btn-sm btn-outline-primary", "Executar novamente");
            rerun.type = "button";
            rerun.dataset.toryRerun = item.id;
            actions.appendChild(rerun);
            if (!favoriteMode) {
                const favorite = window.ToryRenderer.element("button", "btn btn-sm btn-outline-secondary", "Favoritar");
                favorite.type = "button";
                favorite.dataset.toryFavoriteHistory = item.id;
                actions.appendChild(favorite);
            }
            const remove = window.ToryRenderer.element("button", "btn btn-sm btn-outline-secondary", "Excluir");
            remove.type = "button";
            remove.dataset[favoriteMode ? "toryRemoveFavorite" : "toryRemoveHistory"] = item.id;
            actions.appendChild(remove);
            article.appendChild(actions);
            return article;
        }

        function renderHistory() {
            elements.history.replaceChildren();
            toryState.historico.forEach(function (item) { elements.history.appendChild(createRecord(item, false)); });
            elements.historyEmpty.classList.toggle("d-none", toryState.historico.length > 0);
        }

        function renderFavorites() {
            elements.favorites.replaceChildren();
            toryState.favoritos.forEach(function (item) { elements.favorites.appendChild(createRecord(item, true)); });
            elements.favoritesEmpty.classList.toggle("d-none", toryState.favoritos.length > 0);
        }

        function favorite(question, summary, response) {
            question = String(question || "").trim();
            if (!question) return;
            if (toryState.favoritos.some(function (item) { return item.pergunta === question; })) {
                announce("Esta consulta já está nos favoritos.");
                return;
            }
            toryState.favoritos.unshift({
                id: String(Date.now()) + String(Math.random()).slice(2),
                pergunta: question,
                resumo: String(summary || "Consulta favoritada").slice(0, 240),
                data: new Date(),
                resposta: response || null,
            });
            renderFavorites();
            setVisualState("success", 1800);
            announce("Consulta adicionada aos favoritos desta sessão.");
        }

        async function submitQuestion(question) {
            question = String(question || "").trim();
            if (!question || toryState.processando) return;
            await toryState.reinicioContexto;
            if (toryState.falhaReinicioContexto) {
                announce("Atualize a página antes de iniciar uma nova conversa.");
                return;
            }

            activateTab("conversa");
            elements.suggestions.classList.add("d-none");
            const sentAt = new Date();
            addMessage(window.ToryRenderer.userMessage(question, sentAt));
            addMessage(window.ToryRenderer.loadingMessage());
            toryState.mensagens.push({tipo: "usuario", conteudo: question, criadaEm: sentAt});
            toryState.perguntaAtual = question;
            elements.input.value = "";
            autoResize();
            setProcessing(true);
            const controller = new AbortController();
            toryState.requisicao = controller;

            try {
                const data = await window.ToryApi.ask(apiUrl, question, controller.signal);
                removeLoading();
                addMessage(window.ToryRenderer.botMessage(data, question, new Date()));
                setVisualState(
                    responseNeedsAttention(data) ? "attention" : "responding",
                    responseNeedsAttention(data) ? 4000 : 2200
                );
                toryState.mensagens.push({tipo: "tory", conteudo: data, criadaEm: new Date()});
                toryState.resultadoAtual = data;
                toryState.conversaId = data.conversa_id || toryState.conversaId;
                addHistory(question, data);
                if (window.ToryRenderer.hasStructuredResults(data)) {
                    results.setResponse(data);
                    activateTab("resultados");
                    announce("Resposta recebida. O resultado detalhado foi aberto.");
                } else {
                    announce("Resposta da Tory recebida.");
                }
            } catch (error) {
                removeLoading();
                if (error && error.name === "AbortError") {
                    addMessage(window.ToryRenderer.errorMessage("Processamento interrompido.", new Date()));
                    setVisualState("neutral");
                    announce("Processamento interrompido.");
                } else {
                    const message = error && error.message ? error.message : "Não foi possível processar a consulta neste momento.";
                    addMessage(window.ToryRenderer.errorMessage(message, new Date()));
                    setVisualState("attention", 4000);
                    announce(message);
                }
            } finally {
                if (toryState.requisicao === controller) toryState.requisicao = null;
                setProcessing(false);
                elements.input.focus();
            }
        }

        function clearConversation() {
            if (toryState.requisicao) toryState.requisicao.abort();
            elements.messages.querySelectorAll("[data-tory-dynamic]").forEach(function (node) { node.remove(); });
            elements.suggestions.classList.remove("d-none");
            toryState.mensagens = [];
            toryState.resultadoAtual = null;
            toryState.conversaId = null;
            results.clear();
            activateTab("conversa");
            toryState.falhaReinicioContexto = false;
            toryState.reinicioContexto = window.ToryApi.clearContext(apiUrl).catch(function () {
                toryState.falhaReinicioContexto = true;
                setVisualState("attention", 4000);
                announce("A conversa visual foi limpa, mas o contexto do servidor não pôde ser reiniciado.");
            });
            setVisualState("success", 1800);
            announce("Conversa limpa.");
            elements.input.focus();
        }

        document.querySelectorAll("[data-tory-open]").forEach(function (button) {
            button.addEventListener("click", function () {
                elements.minimized.classList.add("d-none");
                toryState.minimizada = false;
                modal.show();
            });
        });
        document.querySelector("[data-tory-dismiss-minimized]").addEventListener("click", function () {
            elements.minimized.classList.add("d-none");
            toryState.minimizada = false;
            elements.toggle.focus();
        });
        document.querySelector("[data-tory-minimize]").addEventListener("click", function () {
            toryState.minimizada = true;
            modal.hide();
        });
        document.querySelector("[data-tory-clear]").addEventListener("click", clearConversation);

        modalElement.addEventListener("shown.bs.modal", function () {
            toryState.aberta = true;
            elements.input.focus();
        });
        modalElement.addEventListener("hidden.bs.modal", function () {
            toryState.aberta = false;
            if (toryState.minimizada) elements.minimized.classList.remove("d-none");
            elements.toggle.focus();
        });

        elements.tabs.forEach(function (tab, index) {
            tab.addEventListener("click", function () { activateTab(tab.dataset.toryTab); });
            tab.addEventListener("keydown", function (event) {
                if (event.key !== "ArrowRight" && event.key !== "ArrowLeft") return;
                event.preventDefault();
                const direction = event.key === "ArrowRight" ? 1 : -1;
                const next = (index + direction + elements.tabs.length) % elements.tabs.length;
                activateTab(elements.tabs[next].dataset.toryTab, true);
            });
        });

        elements.form.addEventListener("submit", function (event) {
            event.preventDefault();
            submitQuestion(elements.input.value);
        });
        elements.input.addEventListener("input", function () {
            autoResize();
            if (!toryState.processando && toryState.estadoVisual === "attention") {
                setVisualState("neutral");
            }
        });
        elements.input.addEventListener("keydown", function (event) {
            if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
                event.preventDefault();
                elements.form.requestSubmit();
            }
        });
        elements.stop.addEventListener("click", function () {
            if (toryState.requisicao) toryState.requisicao.abort();
        });

        modalElement.addEventListener("click", function (event) {
            const suggestion = event.target.closest("[data-tory-suggestion]");
            if (suggestion) {
                elements.input.value = suggestion.dataset.torySuggestion || "";
                autoResize();
                elements.input.focus();
                return;
            }
            const openResults = event.target.closest("[data-tory-open-results]");
            if (openResults) {
                activateTab("resultados");
                return;
            }
            const questionAction = event.target.closest("[data-tory-question]");
            if (questionAction) {
                submitQuestion(questionAction.dataset.toryQuestion);
                return;
            }
            const copy = event.target.closest("[data-tory-copy]");
            if (copy) {
                if (!navigator.clipboard || !navigator.clipboard.writeText) {
                    announce("A cópia não está disponível neste navegador.");
                    return;
                }
                navigator.clipboard.writeText(copy.dataset.toryCopy || "").then(function () {
                    setVisualState("success", 1800);
                    announce("Resposta copiada.");
                }).catch(function () {
                    setVisualState("attention", 4000);
                    announce("Não foi possível copiar a resposta.");
                });
                return;
            }
            const favoriteButton = event.target.closest("[data-tory-favorite]");
            if (favoriteButton) {
                favorite(favoriteButton.dataset.toryFavorite, favoriteButton.dataset.toryFavoriteAnswer, null);
                return;
            }
            const rerun = event.target.closest("[data-tory-rerun]");
            if (rerun) {
                const item = toryState.historico.concat(toryState.favoritos).find(function (record) { return record.id === rerun.dataset.toryRerun; });
                if (item) submitQuestion(item.pergunta);
                return;
            }
            const favoriteHistory = event.target.closest("[data-tory-favorite-history]");
            if (favoriteHistory) {
                const item = toryState.historico.find(function (record) { return record.id === favoriteHistory.dataset.toryFavoriteHistory; });
                if (item) favorite(item.pergunta, item.resumo, item.resposta);
                return;
            }
            const removeHistory = event.target.closest("[data-tory-remove-history]");
            if (removeHistory) {
                toryState.historico = toryState.historico.filter(function (item) { return item.id !== removeHistory.dataset.toryRemoveHistory; });
                renderHistory();
                return;
            }
            const removeFavorite = event.target.closest("[data-tory-remove-favorite]");
            if (removeFavorite) {
                toryState.favoritos = toryState.favoritos.filter(function (item) { return item.id !== removeFavorite.dataset.toryRemoveFavorite; });
                renderFavorites();
            }
        });

        renderHistory();
        renderFavorites();
        activateTab("conversa");
        setVisualState("neutral");
        window.toryState = toryState;
    });
}());
