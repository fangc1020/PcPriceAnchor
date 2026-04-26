from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from price_monitor.config.settings import settings

engine = create_async_engine(settings.database_url, echo=False, pool_size=5, max_overflow=10)

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_session() -> AsyncSession:
    async with async_session() as session:
        yield session
