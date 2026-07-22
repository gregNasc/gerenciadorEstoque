(function () {
    "use strict";

    class ToryApiError extends Error {
        constructor(message, code, status) {
            super(message);
            this.name = "ToryApiError";
            this.code = code || "processamento";
            this.status = status || 0;
        }
    }

    function csrfToken() {
        const input = document.querySelector("#tory-form [name=csrfmiddlewaretoken]");
        return input ? input.value : "";
    }

    async function post(url, body, signal) {
        const response = await fetch(url, {
            method: "POST",
            credentials: "same-origin",
            signal: signal,
            headers: {
                "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
                "X-CSRFToken": csrfToken(),
                "X-Requested-With": "XMLHttpRequest",
            },
            body: new URLSearchParams(body),
        });

        let data = null;
        try {
            data = await response.json();
        } catch (error) {
            data = null;
        }

        if (!response.ok || !data || data.sucesso === false) {
            let message = data && (data.mensagem || data.resposta);
            let code = data && data.erro && data.erro.codigo;
            if (response.status === 401 || (response.redirected && !data)) {
                message = "Sua sessão expirou. Atualize a página e entre novamente.";
                code = "sessao_expirada";
            } else if (response.status === 403) {
                message = message || "Você não possui permissão para consultar essas informações.";
                code = code || "permissao";
            }
            throw new ToryApiError(
                message || "Não foi possível processar a consulta neste momento.",
                code,
                response.status
            );
        }
        return data;
    }

    window.ToryApi = {
        ask: function (url, question, signal) {
            return post(url, {pergunta: question}, signal);
        },
        clearContext: function (url) {
            return post(url, {acao: "limpar_contexto"});
        },
        ToryApiError: ToryApiError,
    };
}());
