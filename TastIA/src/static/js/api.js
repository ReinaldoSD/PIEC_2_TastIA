
const TastIAApi = (() => {
    async function requisicao(url, opcoes = {}) {
        const configuracao = {
            method: opcoes.method || "GET",
            credentials: "same-origin",
            headers: {
                Accept: "application/json",
                "X-Requested-With": "XMLHttpRequest",
                ...(opcoes.headers || {})
            }
        };

        if (opcoes.body instanceof FormData) {
            configuracao.body = opcoes.body;
        } else if (opcoes.body !== undefined) {
            configuracao.headers["Content-Type"] = "application/json";
            configuracao.body = JSON.stringify(opcoes.body);
        }

        let resposta;

        try {
            resposta = await fetch(url, configuracao);
        } catch {
            throw new Error(
                "Não foi possível conectar ao servidor. Verifique se o TastIA está em execução."
            );
        }

        const tipoConteudo = resposta.headers.get("content-type") || "";
        let dados = {};

        if (tipoConteudo.includes("application/json")) {
            try {
                dados = await resposta.json();
            } catch {
                throw new Error("O servidor retornou uma resposta inválida.");
            }
        }

        if (resposta.status === 401) {
            const erro = new Error("Sua sessão expirou. Entre novamente.");
            erro.status = 401;
            erro.dados = dados;

            window.location.href = "/login";
            throw erro;
        }

        if (!resposta.ok) {
            const erro = new Error(
                dados.erro ||
                dados.mensagem ||
                `Erro na comunicação com o servidor (${resposta.status}).`
            );

            erro.status = resposta.status;
            erro.dados = dados;

            throw erro;
        }

        return dados;
    }

    return {
        get(url) {
            return requisicao(url);
        },

        post(url, dados) {
            return requisicao(url, {
                method: "POST",
                body: dados
            });
        },

        delete(url) {
            return requisicao(url, {
                method: "DELETE"
            });
        }
    };
})();
