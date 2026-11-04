import { NextRequest, NextResponse } from 'next/server';
import { getRankings } from '@/lib/db';

export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const portfolio = searchParams.get('portfolio') || 'unified';

  try {
    const data = await getRankings(portfolio);
    return NextResponse.json({
      success: true,
      portfolio,
      count: data.length,
      data,
    });
  } catch (err: any) {
    return NextResponse.json(
      { success: false, error: err.message || 'Failed to fetch rankings' },
      { status: 500 }
    );
  }
}
