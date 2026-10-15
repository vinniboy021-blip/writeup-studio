# Guia do usuário

## Entrar e organizar o workspace

Crie uma conta ou entre com suas credenciais. Documentos começam privados. O Dashboard mostra os recursos que você pode acessar, progresso e atividade registrada; uma instalação nova apresenta estados vazios, não competições simuladas.

Em **Competições**, registre nome, plataforma, descrição, datas, modalidade, tags e visibilidade. Em **Desafios**, vincule competição, categoria, dificuldade, pontuação, status, referências e responsáveis. Categorias padrão podem ser complementadas por categorias próprias/de equipe.

**Times** permite criar equipe, preparar convite com papel e copiar o token para o participante. A aceitação exige conta com o email do convite. O token expira e não pode ser reutilizado. O envio de email não é um serviço obrigatório; o gestor compartilha o convite pelo canal de sua escolha. Os papéis são verificados no servidor, inclusive quando alguém acessa uma URL diretamente.

## Produzir um writeup

Abra um documento existente ou crie um por template/desafio/workspace. Os templates contêm estruturas vazias para CTF, HTB, TryHackMe, PicoCTF, pentest, vulnerabilidade, CVE, bug bounty, forense e engenharia reversa. Preencha somente observações e comandos cuja origem possa identificar.

Edite em Markdown ou rich-text, acrescente/remova/reorganize seções e consulte o preview. Código deve informar linguagem; diagramas Mermaid são renderizados com configuração restritiva no navegador. Evidências podem ser vinculadas a uma seção. **Autosave** indica salvamento/erro/conflito; fechar uma sessão com mudanças pendentes exige cuidado com o aviso do editor.

O rascunho local ajuda na recuperação após falha de rede. Ele não substitui backup do servidor e pode conter texto privado: evite navegador compartilhado e limpe rascunhos antes de deixar o dispositivo com outra pessoa.

## Resolver conflitos e revisões

Se outra sessão salvou primeiro, o editor preserva seu rascunho e mostra conflito. Compare a versão remota com a local, selecione o conteúdo desejado e confirme a resolução usando a versão atual. Não copie conteúdo antigo sobre mudanças de colegas sem revisão.

O histórico permite comparar versões e restaurar uma revisão. Restaurar cria uma versão nova; o histórico anterior permanece. Alterar o documento invalida aprovação prévia. Comentários podem se referir a seções e ser resolvidos por quem tem permissão.

## Evidências e anotações

Envie um arquivo permitido, descreva a origem e informe a captura quando conhecida. **Captura declarada** é informação do autor; **recebimento do servidor** registra a entrada no sistema. SHA-256 identifica os bytes originais.

Abra a evidência na galeria/lista. Em imagens, use setas, retângulos, círculos, linhas, texto, destaque, passos, recorte, desfoque e redação. Desfazer/refazer e camadas preservam o desenho editável. Salvar gera uma imagem derivada; o download do original continua acessível somente aos autorizados. Confirme o derivado antes de publicar informação sensível: desfoque não substitui uma redação opaca quando o conteúdo precisa ser removido visualmente.

A timeline registra upload, metadados, anotação, associação e publicação. Use comparação/versões para revisar derivados e nunca descreva uma anotação como se estivesse presente na captura original.

## Revisar, exportar e publicar

Selecione outro usuário habilitado para revisão. Um revisor aprova ou solicita mudanças na versão corrente. Publicação usa snapshot aprovado; público exige confirmação explícita. Imagens públicas devem ser selecionadas e derivadas, mantendo originais protegidos. Uma publicação pública compartilha o texto selecionado: verifique flags, tokens e informações privadas antes de confirmar.

Exportações Markdown, HTML, PDF e JSON mostram estado de processamento. Escolha capa, marca, tema, cabeçalho/rodapé e inclusão de evidências. Anexos originais não são incluídos automaticamente. Baixe a exportação concluída; um job cancelado/falho não deve ser apresentado como arquivo pronto.

## IA e Kali

IA só aparece como disponível quando a operação habilita um provedor. Selecione fontes autorizadas, peça ajuda de documentação e revise fatos, hipóteses e lacunas. Um provedor externo pede consentimento antes de receber conteúdo.

Kali MCP permite coletar hash, tipo, strings e resumo estrutural de uma evidência autorizada. Confirme a operação; o resultado vira outra evidência com proveniência e hash. A saída do ambiente não é uma conclusão automática sobre a resolução do desafio.
