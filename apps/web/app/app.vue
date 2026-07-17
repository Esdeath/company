<template>
  <div class="site-shell">
    <header class="masthead">
      <a
        class="brand"
        href="/"
        aria-label="企业研究资料库首页"
      >
        <span class="brand__name">企业研究</span>
        <span class="brand__note">Research library</span>
      </a>

      <a
        class="admin-link admin-link--compact"
        href="/admin/"
      >
        进入管理端
        <span aria-hidden="true">↗</span>
      </a>
    </header>

    <main>
      <section
        class="intro"
        aria-labelledby="page-title"
      >
        <p class="status">
          <span class="status__mark" aria-hidden="true" />
          公开端工程骨架
        </p>
        <h1 id="page-title">
          企业研究资料库
        </h1>
        <p class="intro__summary">
          当前里程碑先建立清晰、可验证的访问边界，为后续公开研究资料提供稳定入口。
        </p>
      </section>

      <section
        class="boundaries"
        aria-labelledby="boundary-title"
      >
        <div class="section-heading">
          <p>System boundary</p>
          <h2 id="boundary-title">
            三层各司其职
          </h2>
        </div>

        <dl class="boundary-list">
          <div class="boundary-list__item">
            <dt>公开端</dt>
            <dd>提供公开研究资料的阅读界面；此阶段只建立运行骨架，不填充研究条目。</dd>
          </div>
          <div class="boundary-list__item">
            <dt>管理端</dt>
            <dd>
              承载内部整理与发布流程，与公开页面保持分离。
              <a class="admin-link" href="/admin/">前往管理端 <span aria-hidden="true">↗</span></a>
            </dd>
          </div>
          <div class="boundary-list__item">
            <dt>API</dt>
            <dd>提供结构化数据接口，由服务端独立演进；公开端只消费约定后的能力。</dd>
          </div>
        </dl>
      </section>
    </main>

    <footer class="footer">
      <p>公开阅读 · 内部管理 · 数据服务</p>
      <p>当前仅建立工程边界</p>
    </footer>
  </div>
</template>
